"""
https://www.youtube.com/watch?v=tNYoZkMBV8k

Document Control System (Multi-Tenant, Unified DB, ISO 17025 + 21 CFR Part 11)

The primary focus for improvement lies in enhancing data integrity, version control enforcement, and explicit 21 CFR Part 11 electronic signature requirements......
Version Control ISO 17025...
"""

from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import FileExtensionValidator
from django.utils import timezone
from datetime import timedelta

User = get_user_model()


class DocumentCategory(models.Model):
    """Categories for organizing documents (SOPs, Forms, Policies, etc.)"""
    vendor = models.ForeignKey('tenants.Vendor', on_delete=models.CASCADE, related_name='document_categories', null=True, blank=True)
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, default="SOP")  # e.g., SOP, FORM, POLICY
    description = models.TextField(blank=True)
    requires_training = models.BooleanField(default=False)
    retention_period_days = models.IntegerField(default=2555)  # 7 years default
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_doc_categories')
    
    class Meta:
        verbose_name_plural = "Document Categories"
        ordering = ['code', 'name']
        unique_together = ['vendor', 'code']
    
    def __str__(self):
        return f"{self.code} - {self.name}"


class ControlledDocument(models.Model):
    """Main document table with version control and compliance features"""
    
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('under_review', 'Under Review'),
        ('approved', 'Approved'),
        ('effective', 'Effective'),
        ('obsolete', 'Obsolete'),
        ('retired', 'Retired'),
    ]
    
    vendor = models.ForeignKey('tenants.Vendor', on_delete=models.CASCADE, related_name='controlled_documents')
    category = models.ForeignKey(DocumentCategory, on_delete=models.PROTECT, related_name='documents')
    
    # Document Identification
    document_number = models.CharField(max_length=50)  # e.g., SOP-QC-001
    title = models.CharField(max_length=255)
    version = models.CharField(max_length=20, default='1.0')
    
    # Document Details
    description = models.TextField(blank=True)
    purpose = models.TextField(blank=True)
    scope = models.TextField(blank=True)
    
    # Status and Lifecycle
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    effective_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    review_frequency_days = models.IntegerField(default=365)  # Annual review
    next_review_date = models.DateField(null=True, blank=True)
    
    # File Management
    file = models.FileField(
        upload_to='documents/%Y/%m/',
        validators=[FileExtensionValidator(allowed_extensions=['pdf', 'docx', 'xlsx', 'txt'])],
        null=True,
        blank=True
    )
    file_size = models.IntegerField(null=True, blank=True)  # in bytes
    checksum = models.CharField(max_length=64, blank=True)  # SHA-256 for integrity
    
    # Ownership and Responsibility
    owner = models.ForeignKey(User, on_delete=models.PROTECT, related_name='owned_documents')
    department = models.CharField(max_length=100, blank=True)
    
    # Compliance Fields (21 CFR Part 11)
    requires_electronic_signature = models.BooleanField(default=True)
    requires_training = models.BooleanField(default=False)
    is_controlled = models.BooleanField(default=True)
    
    # Metadata
    keywords = models.CharField(max_length=255, blank=True, help_text="Comma-separated keywords")
    is_active = models.BooleanField(default=True)
    supersedes = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='superseded_by')
    
    # Audit Trail
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_documents')
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='updated_documents')
    
    class Meta:
        ordering = ['-created_at']
        unique_together = ['vendor', 'document_number', 'version']
        indexes = [
            models.Index(fields=['vendor', 'status']),
            models.Index(fields=['document_number']),
            models.Index(fields=['next_review_date']),
        ]
    
    def __str__(self):
        return f"{self.document_number} v{self.version} - {self.title}"
    
    def get_full_identifier(self):
        return f"{self.document_number}-v{self.version}"
    
    def is_due_for_review(self):
        if self.next_review_date:
            return timezone.now().date() >= self.next_review_date
        return False
    
    def calculate_next_review_date(self):
        if self.effective_date:
            return self.effective_date + timedelta(days=self.review_frequency_days)
        return None


class DocumentVersion(models.Model):
    """Track all versions and changes to documents"""
    vendor = models.ForeignKey('tenants.Vendor', on_delete=models.CASCADE, related_name='document_versions')
    document = models.ForeignKey(ControlledDocument, on_delete=models.CASCADE, related_name='versions')
    
    version_number = models.CharField(max_length=20)
    change_description = models.TextField(help_text="Summary of changes made in this version")
    change_type = models.CharField(
        max_length=20,
        choices=[
            ('major', 'Major Revision'),
            ('minor', 'Minor Revision'),
            ('editorial', 'Editorial Change'),
        ],
        default='minor'
    )
    
    file = models.FileField(upload_to='documents/versions/%Y/%m/')
    file_size = models.IntegerField()
    checksum = models.CharField(max_length=64)
    
    effective_date = models.DateField(null=True, blank=True)
    obsolete_date = models.DateField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='versioned_documents')
    
    class Meta:
        ordering = ['-created_at']
        unique_together = ['document', 'version_number']
    
    def __str__(self):
        return f"{self.document.document_number} - Version {self.version_number}"


class DocumentReview(models.Model):
    """Document review and approval workflow"""
    
    REVIEW_STATUS_CHOICES = [
        ('pending', 'Pending Review'),
        ('in_progress', 'In Progress'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('on_hold', 'On Hold'),
    ]
    
    vendor = models.ForeignKey('tenants.Vendor', on_delete=models.CASCADE, related_name='document_reviews')
    document = models.ForeignKey(ControlledDocument, on_delete=models.CASCADE, related_name='reviews')
    
    review_type = models.CharField(
        max_length=20,
        choices=[
            ('initial', 'Initial Review'),
            ('periodic', 'Periodic Review'),
            ('change', 'Change Control Review'),
            ('audit', 'Audit Review'),
        ]
    )
    
    status = models.CharField(max_length=20, choices=REVIEW_STATUS_CHOICES, default='pending')
    
    # Review Assignment
    reviewer = models.ForeignKey(User, on_delete=models.PROTECT, related_name='assigned_reviews')
    approver = models.ForeignKey(User, on_delete=models.PROTECT, related_name='approval_reviews', null=True, blank=True)
    
    # Review Details
    due_date = models.DateField()
    comments = models.TextField(blank=True)
    recommendations = models.TextField(blank=True)
    
    # Review Completion
    review_completed_at = models.DateTimeField(null=True, blank=True)
    approval_completed_at = models.DateTimeField(null=True, blank=True)
    
    # Audit Trail
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='initiated_reviews')
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['vendor', 'status']),
            models.Index(fields=['due_date']),
        ]
    
    def __str__(self):
        return f"{self.document.document_number} - {self.review_type} Review"
    
    def is_overdue(self):
        return timezone.now().date() > self.due_date and self.status == 'pending'


class DocumentApproval(models.Model):
    """Electronic signature and approval records (21 CFR Part 11 compliance)"""
    
    vendor = models.ForeignKey('tenants.Vendor', on_delete=models.CASCADE, related_name='document_approvals')
    document = models.ForeignKey(ControlledDocument, on_delete=models.CASCADE, related_name='approvals')
    review = models.ForeignKey(DocumentReview, on_delete=models.SET_NULL, null=True, blank=True, related_name='approvals')
    
    # Approval Details
    approval_type = models.CharField(
        max_length=20,
        choices=[
            ('author', 'Author'),
            ('reviewer', 'Reviewer'),
            ('approver', 'Approver'),
            ('quality', 'Quality Assurance'),
        ]
    )
    
    approver = models.ForeignKey(User, on_delete=models.PROTECT, related_name='document_approvals')
    approval_status = models.CharField(
        max_length=20,
        choices=[
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
        ]
    )
    
    # Electronic Signature (21 CFR Part 11)
    signature = models.CharField(max_length=255)  # Encrypted signature
    reason_for_signature = models.CharField(max_length=255)
    comments = models.TextField(blank=True)
    
    # Compliance Fields
    ip_address = models.GenericIPAddressField()
    user_agent = models.CharField(max_length=255, blank=True)
    
    # Timestamp
    signed_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-signed_at']
        indexes = [
            models.Index(fields=['vendor', 'document']),
        ]
    
    def __str__(self):
        return f"{self.document.document_number} - {self.approval_type} by {self.approver.get_full_name()}"


class DocumentDistribution(models.Model):
    """Track document distribution and acknowledgment"""
    vendor = models.ForeignKey('tenants.Vendor', on_delete=models.CASCADE, related_name='document_distributions')
    document = models.ForeignKey(ControlledDocument, on_delete=models.CASCADE, related_name='distributions')
    
    # Distribution Details
    distributed_to = models.ForeignKey(User, on_delete=models.PROTECT, related_name='received_documents')
    distribution_method = models.CharField(
        max_length=20,
        choices=[
            ('email', 'Email'),
            ('portal', 'Portal Access'),
            ('print', 'Printed Copy'),
        ],
        default='portal'
    )
    
    # Acknowledgment
    requires_acknowledgment = models.BooleanField(default=True)
    acknowledged = models.BooleanField(default=False)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    acknowledgment_signature = models.CharField(max_length=255, blank=True)
    
    # Audit Trail
    distributed_at = models.DateTimeField(auto_now_add=True)
    distributed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='distributed_documents')
    
    class Meta:
        ordering = ['-distributed_at']
        unique_together = ['document', 'distributed_to']
    
    def __str__(self):
        return f"{self.document.document_number} distributed to {self.distributed_to.get_full_name()}"


class DocumentTraining(models.Model):
    """Track training requirements and completion for documents (ISO 17025)"""
    vendor = models.ForeignKey('tenants.Vendor', on_delete=models.CASCADE, related_name='document_trainings')
    document = models.ForeignKey(ControlledDocument, on_delete=models.CASCADE, related_name='trainings')
    
    # Training Details
    trainee = models.ForeignKey(User, on_delete=models.PROTECT, related_name='document_trainings')
    training_type = models.CharField(
        max_length=20,
        choices=[
            ('initial', 'Initial Training'),
            ('refresher', 'Refresher Training'),
            ('update', 'Update Training'),
        ]
    )
    
    # Training Status
    status = models.CharField(
        max_length=20,
        choices=[
            ('required', 'Required'),
            ('in_progress', 'In Progress'),
            ('completed', 'Completed'),
            ('expired', 'Expired'),
        ],
        default='required'
    )
    
    # Training Completion
    completed_at = models.DateTimeField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    assessment_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    assessment_passed = models.BooleanField(default=False)
    
    # Training Record
    trainer = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='conducted_trainings')
    training_duration_minutes = models.IntegerField(null=True, blank=True)
    notes = models.TextField(blank=True)
    
    # Audit Trail
    assigned_at = models.DateTimeField(auto_now_add=True)
    assigned_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='assigned_trainings')
    
    class Meta:
        ordering = ['-assigned_at']
        unique_together = ['document', 'trainee', 'training_type']
    
    def __str__(self):
        return f"{self.document.document_number} - Training for {self.trainee.get_full_name()}"


class DocumentAuditLog(models.Model):
    """Complete audit trail for all document activities (21 CFR Part 11)"""
    vendor = models.ForeignKey('tenants.Vendor', on_delete=models.CASCADE, related_name='document_audit_logs')
    document = models.ForeignKey(ControlledDocument, on_delete=models.CASCADE, related_name='audit_logs')
    
    # Action Details
    action = models.CharField(
        max_length=50,
        choices=[
            ('created', 'Document Created'),
            ('updated', 'Document Updated'),
            ('viewed', 'Document Viewed'),
            ('downloaded', 'Document Downloaded'),
            ('printed', 'Document Printed'),
            ('approved', 'Document Approved'),
            ('rejected', 'Document Rejected'),
            ('obsoleted', 'Document Obsoleted'),
            ('retired', 'Document Retired'),
            ('distributed', 'Document Distributed'),
        ]
    )
    
    # User and Context
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    user_full_name = models.CharField(max_length=255)  # Store for history
    
    # Details
    description = models.TextField()
    old_value = models.TextField(blank=True)
    new_value = models.TextField(blank=True)
    
    # System Information
    ip_address = models.GenericIPAddressField()
    user_agent = models.CharField(max_length=255, blank=True)
    
    # Timestamp
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['vendor', 'document']),
            models.Index(fields=['timestamp']),
            models.Index(fields=['action']),
        ]
    
    def __str__(self):
        return f"{self.action} - {self.document.document_number} by {self.user_full_name}"


class DocumentReference(models.Model):
    """Track references and relationships between documents"""
    vendor = models.ForeignKey('tenants.Vendor', on_delete=models.CASCADE, related_name='document_references')
    source_document = models.ForeignKey(ControlledDocument, on_delete=models.CASCADE, related_name='references_made')
    referenced_document = models.ForeignKey(ControlledDocument, on_delete=models.CASCADE, related_name='referenced_by')
    
    reference_type = models.CharField(
        max_length=20,
        choices=[
            ('related', 'Related Document'),
            ('supersedes', 'Supersedes'),
            ('supplement', 'Supplementary Document'),
            ('procedure', 'Referenced Procedure'),
        ]
    )
    
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    
    class Meta:
        unique_together = ['source_document', 'referenced_document']
    
    def __str__(self):
        return f"{self.source_document.document_number} references {self.referenced_document.document_number}"




# from django.db import models
# from django.conf import settings
# from django.utils import timezone

# # -------------------------------------------------------------
# # 1. BASE MIXINS (REFINED)
# # -------------------------------------------------------------
# class TenantOwnedModel(models.Model):
#     # Ensures every record belongs to a tenant (Multi-tenant, unified DB)
#     tenant = models.ForeignKey("tenants.Vendor", on_delete=models.CASCADE)
#     class Meta:
#         abstract = True


# class FullAuditStamp(models.Model):
#     """For mutable administrative records (e.g., Document, Category)."""
#     created_at = models.DateTimeField(auto_now_add=True)
#     updated_at = models.DateTimeField(auto_now=True)
#     created_by = models.ForeignKey(
#         settings.AUTH_USER_MODEL,
#         null=True, blank=True,
#         on_delete=models.SET_NULL,
#         related_name='created_%(class)s_records'
#     )
#     updated_by = models.ForeignKey( # Necessary for tracing changes to mutable data
#         settings.AUTH_USER_MODEL,
#         null=True, blank=True,
#         on_delete=models.SET_NULL,
#         related_name='updated_%(class)s_records'
#     )
#     class Meta:
#         abstract = True


# class ImmutableAuditStamp(models.Model):
#     """For immutable, regulated records (e.g., Version, Signature, Training)."""
#     created_at = models.DateTimeField(auto_now_add=True)
#     created_by = models.ForeignKey(
#         settings.AUTH_USER_MODEL,
#         null=True, blank=True,
#         on_delete=models.SET_NULL,
#         related_name='created_%(class)s_records'
#     )
#     class Meta:
#         abstract = True


# # -------------------------------------------------------------
# # 2. CONTROLLED DOCUMENT CATEGORY
# # -------------------------------------------------------------
# class DocumentCategory(TenantOwnedModel, FullAuditStamp): # <-- Uses FullAuditStamp
#     name = models.CharField(max_length=150)
#     description = models.TextField(blank=True)

#     class Meta:
#         unique_together = ('tenant', 'name')
#         verbose_name = "Document Category"
#         verbose_name_plural = "Document Categories"

#     def __str__(self):
#         return self.name


# # -------------------------------------------------------------
# # 3. DOCUMENT (Logical container for versions)
# # -------------------------------------------------------------
# class Document(TenantOwnedModel, FullAuditStamp): # <-- Uses FullAuditStamp
#     STATUS_CHOICES = [
#         ('ACTIVE', 'Active'),
#         ('INACTIVE', 'Inactive'),
#     ]

#     title = models.CharField(max_length=255)
#     category = models.ForeignKey(DocumentCategory, on_delete=models.PROTECT)
#     status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE')

#     # Pointer to the currently effective version
#     current_version = models.ForeignKey('DocumentVersion', null=True, blank=True, on_delete=models.SET_NULL, related_name='document_versn',) 
    
#     effective_date = models.DateField(null=True, blank=True)
#     review_due_date = models.DateField(null=True, blank=True)

#     # 21 CFR 11: document ownership
#     owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='owned_documents')

#     class Meta:
#         unique_together = ('tenant', 'title')
#         ordering = ['title']

#     def __str__(self):
#         return self.title

# # -------------------------------------------------------------
# # 4. DOCUMENT VERSION (Regulated, immutable once approved)
# # -------------------------------------------------------------
# class DocumentVersion(TenantOwnedModel, ImmutableAuditStamp):
#     STATUS_CHOICES = [
#         ('DRAFT', 'Draft'),
#         ('REVIEW', 'In Review'),
#         ('APPROVED', 'Approved'),
#         ('REJECTED', 'Rejected'),
#         ('ARCHIVED', 'Archived'),
#     ]

#     document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='versions')
#     version_number = models.CharField(max_length=50)
#     file = models.FileField(upload_to='doc_control/%Y/%m/%d/')
#     file_checksum = models.CharField(max_length=64, blank=True) # Data Integrity
#     status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
#     change_summary = models.TextField(blank=True)
#     approved_by = models.ForeignKey(
#         settings.AUTH_USER_MODEL,
#         null=True, blank=True,
#         on_delete=models.SET_NULL,
#         related_name='approved_document_versions'
#     )
#     approved_at = models.DateTimeField(null=True, blank=True)

#     # RESTORED: Required by ISO 17025 (Clause 8.3.2d)
#     is_effective = models.BooleanField(default=False) 

#     is_latest_draft = models.BooleanField(default=False, help_text="Identify the single active draft being worked on for a given Document")
#     is_obsolete = models.BooleanField(default=False, help_text="Version as retired/superseded, preventing accidental use of an old document- ISO 17025") 

#     def approve(self, user):
#         self.status = 'APPROVED'
#         self.approved_by = user
#         self.approved_at = timezone.now()
#         self.is_effective = True # To active document
#         self.save()


#     class Meta:
#         unique_together = ('tenant', 'document', 'version_number')
#         ordering = ['-created_at']

#     def __str__(self):
#         return f"{self.document.title} - v{self.version_number}"


# # -------------------------------------------------------------
# # 5. ELECTRONIC SIGNATURES (21 CFR Part 11 requirement)
# # -------------------------------------------------------------
# class ElectronicSignature(TenantOwnedModel, ImmutableAuditStamp):
#     ACTION_CHOICES = [
#         ('REVIEW', 'Review Approval'),
#         ('APPROVAL', 'Final Document Approval'),
#         ('ACK', 'Read & Acknowledge'),
#     ]
    
#     user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
#     document_version = models.ForeignKey(DocumentVersion, on_delete=models.CASCADE)
#     action = models.CharField(max_length=30, choices=ACTION_CHOICES)
#     # Store the cryptographic hash of the user's secondary login credentials (e.g., password hash)
#     # at the time of signing, to prove the two-factor intent.
#     verification_data = models.CharField(max_length=255) # 21 CFR Part 11 Two-Factor
#     signed_at = models.DateTimeField(auto_now_add=True)
#     reason = models.TextField() # 21 CFR Part 11 Signature Meaning/Intent

#     class Meta:
#         ordering = ['-signed_at']

#     def __str__(self):
#         return f"Signature by {self.user} on {self.document_version}"


# # -------------------------------------------------------------
# # 6. AUDIT TRAIL (Regulatory: 21 CFR Part 11 + ISO 17025)
# # -------------------------------------------------------------
# class DocumentAuditTrail(TenantOwnedModel):
#     document_version = models.ForeignKey(DocumentVersion, on_delete=models.CASCADE)
#     action = models.CharField(max_length=200)
#     details = models.JSONField(default=dict)
#     performed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT) 
#     timestamp = models.DateTimeField(auto_now_add=True)

#     class Meta:
#         ordering = ['-timestamp']



# # -------------------------------------------------------------
# # 7. TRAINING ACKNOWLEDGEMENTS (ISO 17025 clause 6.2)
# # -------------------------------------------------------------
# class DocumentTrainingRecord(TenantOwnedModel, ImmutableAuditStamp):
#     user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
#     document_version = models.ForeignKey(DocumentVersion, on_delete=models.CASCADE)

#     class Meta:
#         unique_together = ('user', 'document_version')

#     def __str__(self):
#         return f"{self.user} trained on {self.document_version}"

