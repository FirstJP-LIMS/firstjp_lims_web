"""
https://www.youtube.com/watch?v=tNYoZkMBV8k

Document Control System (Multi-Tenant, Unified DB, ISO 17025 + 21 CFR Part 11)

The primary focus for improvement lies in enhancing data integrity, version control enforcement, and explicit 21 CFR Part 11 electronic signature requirements......
Version Control ISO 17025...
"""
from django.db import models


from django.db import models
from django.conf import settings
from django.utils import timezone

# -------------------------------------------------------------
# 1. BASE MIXINS
# -------------------------------------------------------------
class TenantOwnedModel(models.Model):
    """
    Ensures every record belongs to a tenant.
    Supports: Multi-tenant (unified DB, row-level separation).
    """
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE)

    class Meta:
        abstract = True




class AuditStamp(models.Model):
    """
    Regulatory requirement:
    - ISO/IEC 17025: traceability of actions
    - 21 CFR Part 11: who did what and when
    """
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,related_name='created_%(class)s_records')

    # updated_at = models.DateTimeField(auto_now=True)
    # updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='updated_%(class)s_records')

    class Meta:
        abstract = True


# -------------------------------------------------------------
# 2. CONTROLLED DOCUMENT CATEGORY
# -------------------------------------------------------------
class DocumentCategory(TenantOwnedModel, AuditStamp):
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)

    class Meta:
        unique_together = ('tenant', 'name')
        verbose_name = "Document Category"
        verbose_name_plural = "Document Categories"

    def __str__(self):
        return self.name


# -------------------------------------------------------------
# 3. DOCUMENT (Logical container for versions)
# -------------------------------------------------------------
class Document(TenantOwnedModel, AuditStamp):
    STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('INACTIVE', 'Inactive'),
    ]

    title = models.CharField(max_length=255)
    category = models.ForeignKey(DocumentCategory, on_delete=models.PROTECT)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE')

    # pointer to the currently released version
    current_version = models.ForeignKey('DocumentVersion', null=True, blank=True, on_delete=models.SET_NULL, related_name='document_versn') # OneToOne - Document version strictly attached to a version, Changed to ForeignKey

    effective_date = models.DateField(null=True, blank=True)
    review_due_date = models.DateField(null=True, blank=True)

    # 21 CFR 11: document ownership
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='owned_documents')

    class Meta:
        unique_together = ('tenant', 'title')
        ordering = ['title']

    def __str__(self):
        return self.title


# -------------------------------------------------------------
# 4. DOCUMENT VERSION (Regulated, immutable once approved)
# -------------------------------------------------------------
class DocumentVersion(TenantOwnedModel, AuditStamp):
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('REVIEW', 'In Review'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
        ('ARCHIVED', 'Archived'),
    ]

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='versions')
    version_number = models.CharField(max_length=50)
    file = models.FileField(upload_to='doc_control/%Y/%m/%d/')
    file_checksum = models.CharField(max_length=64, blank=True) # e.g., SHA-256
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    change_summary = models.TextField(blank=True)

    # reviewed_by = models.ManyToManyField(
    #     settings.AUTH_USER_MODEL,
    #     blank=True,
    #     related_name='reviewed_document_versions'
    # )

    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='approved_document_versions'
    )

    approved_at = models.DateTimeField(null=True, blank=True)

    is_latest_draft = models.BooleanField(default=False, help_text="Identify the single active draft being worked on for a given Document")

    # ISO 17025 (Clause 8.3.2f): Explicitly marks a version as retired/superseded, preventing accidental use of an old document.
    is_obsolete = models.BooleanField(default=False, help_text="Version as retired/superseded, preventing accidental use of an old document- ISO 17025") 

    class Meta:
        unique_together = ('tenant', 'document', 'version_number')
        ordering = ['-created_at']

    def approve(self, user):
        self.status = 'APPROVED'
        self.approved_by = user
        self.approved_at = timezone.now()
        self.is_effective = True
        self.save()

    def __str__(self):
        return f"{self.document.title} - v{self.version_number}"


# -------------------------------------------------------------
# 5. ELECTRONIC SIGNATURES (21 CFR Part 11 requirement)
# -------------------------------------------------------------
class ElectronicSignature(TenantOwnedModel, AuditStamp):
    ACTION_CHOICES = [
        ('REVIEW', 'Review Approval'),
        ('APPROVAL', 'Final Document Approval'),
        ('ACK', 'Read & Acknowledge'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    document_version = models.ForeignKey(DocumentVersion, on_delete=models.CASCADE)
    action = models.CharField(max_length=30, choices=ACTION_CHOICES)
    
    # Store the cryptographic hash of the user's secondary login credentials (e.g., password hash)
    # at the time of signing, to prove the two-factor intent.
    verification_data = models.CharField(max_length=255) 
    
    signed_at = models.DateTimeField(auto_now_add=True)
    
    # Required for 21 CFR 11: Mandate the user explains the intent of their signature
    reason = models.TextField() 

    class Meta:
        ordering = ['-signed_at']

    def __str__(self):
        return f"Signature by {self.user} on {self.document_version}"

# -------------------------------------------------------------
# 6. AUDIT TRAIL (Regulatory: 21 CFR Part 11 + ISO 17025)
# -------------------------------------------------------------
class DocumentAuditTrail(TenantOwnedModel):
    document_version = models.ForeignKey(DocumentVersion, on_delete=models.CASCADE)
    action = models.CharField(max_length=200)
    details = models.JSONField(default=dict)
    performed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']


# -------------------------------------------------------------
# 7. TRAINING ACKNOWLEDGEMENTS (ISO 17025 clause 6.2)
# -------------------------------------------------------------
class DocumentTrainingRecord(TenantOwnedModel, AuditStamp):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    document_version = models.ForeignKey(DocumentVersion, on_delete=models.CASCADE)
    acknowledged_at = models.DateTimeField(auto_now_add=True)

    "link to ElectronicSignature for "

    class Meta:
        unique_together = ('tenant', 'user', 'document_version')
        ordering = ['-acknowledged_at']

    def __str__(self):
        return f"{self.user} trained on {self.document_version}"

