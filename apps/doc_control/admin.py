from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from .models import (
    DocumentCategory, ControlledDocument, DocumentVersion,
    DocumentReview, DocumentApproval, DocumentDistribution,
    DocumentTraining, DocumentAuditLog, DocumentReference
)


@admin.register(DocumentCategory)
class DocumentCategoryAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'requires_training', 'retention_period_days', 'is_active', 'created_at']
    list_filter = ['is_active', 'requires_training', 'vendor']
    search_fields = ['name', 'code', 'description']
    readonly_fields = ['created_at', 'created_by']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('vendor', 'name', 'code', 'description')
        }),
        ('Settings', {
            'fields': ('requires_training', 'retention_period_days', 'is_active')
        }),
        ('Audit', {
            'fields': ('created_at', 'created_by'),
            'classes': ('collapse',)
        }),
    )
    
    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


class DocumentVersionInline(admin.TabularInline):
    model = DocumentVersion
    extra = 0
    readonly_fields = ['version_number', 'created_at', 'created_by']
    fields = ['version_number', 'change_type', 'change_description', 'effective_date', 'created_at']
    can_delete = False


class DocumentApprovalInline(admin.TabularInline):
    model = DocumentApproval
    extra = 0
    readonly_fields = ['signed_at', 'signature']
    fields = ['approval_type', 'approver', 'approval_status', 'signed_at']
    can_delete = False


# @admin.register(ControlledDocument)
# class ControlledDocumentAdmin(admin.ModelAdmin):
#     list_display = [
#         'document_number', 'title', 'version', 'status_badge', 
#         'category', 'owner', 'effective_date', 'review_status'
#     ]
#     list_filter = [
#         'status', 'category', 'requires_training', 
#         'is_controlled', 'vendor', 'created_at'
#     ]
#     # search_fields = []
#     readonly_fields = [
#         'created_at', 'created_by', 'updated_at', 'updated_by', 
#         'file_size', 'checksum', 'get_full_identifier'
#     ]
#     autocomplete_fields = ['owner', 'supersedes']
#     date_hierarchy = 'created_at'
#     inlines = [DocumentVersionInline, DocumentApprovalInline]
    
#     fieldsets = (
#         ('Document Identification', {
#             'fields': ('vendor', 'category', 'document_number', 'title', 'version')
#         }),
#         ('Document Content', {
#             'fields': ('description', 'purpose', 'scope', 'file', 'file_size', 'checksum')
#         }),
#         ('Status & Lifecycle', {
#             'fields': (
#                 'status', 'effective_date', 'expiry_date', 
#                 'review_frequency_days', 'next_review_date'
#             )
#         }),
#         ('Ownership', {
#             'fields': ('owner', 'department')
#         }),
#         ('Compliance Settings', {
#             'fields': (
#                 'requires_electronic_signature', 'requires_training', 
#                 'is_controlled', 'supersedes'
#             )
#         }),
#         ('Metadata', {
#             'fields': ('keywords', 'is_active'),
#             'classes': ('collapse',)
#         }),
#         ('Audit Trail', {
#             'fields': ('created_at', 'created_by', 'updated_at', 'updated_by'),
#             'classes': ('collapse',)
#         }),
#     )
    
#     def status_badge(self, obj):
#         colors = {
#             'draft': '#6c757d',
#             'under_review': '#ffc107',
#             'approved': '#17a2b8',
#             'effective': '#28a745',
#             'obsolete': '#dc3545',
#             'retired': '#6c757d',
#         }
#         return format_html(
#             '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px;">{}</span>',
#             colors.get(obj.status, '#6c757d'),
#             obj.get_status_display()
#         )
#     status_badge.short_description = 'Status'
    
#     def review_status(self, obj):
#         if obj.is_due_for_review():
#             return format_html(
#                 '<span style="color: red; font-weight: bold;">⚠ Due for Review</span>'
#             )
#         return format_html('<span style="color: green;">✓ Current</span>')
#     review_status.short_description = 'Review Status'
    
#     def save_model(self, request, obj, form, change):
#         if not change:
#             obj.created_by = request.user
#         obj.updated_by = request.user
#         super().save_model(request, obj, form, change)


@admin.register(DocumentVersion)
class DocumentVersionAdmin(admin.ModelAdmin):
    list_display = ['document', 'version_number', 'change_type', 'effective_date', 'created_at', 'created_by']
    list_filter = ['change_type', 'vendor', 'created_at']
    search_fields = ['document__document_number', 'document__title', 'change_description']
    readonly_fields = ['created_at', 'created_by', 'file_size', 'checksum']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Version Information', {
            'fields': ('vendor', 'document', 'version_number', 'change_type')
        }),
        ('Changes', {
            'fields': ('change_description', 'effective_date', 'obsolete_date')
        }),
        ('File', {
            'fields': ('file', 'file_size', 'checksum')
        }),
        ('Audit', {
            'fields': ('created_at', 'created_by'),
            'classes': ('collapse',)
        }),
    )
    
    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(DocumentReview)
class DocumentReviewAdmin(admin.ModelAdmin):
    list_display = [
        'document', 'review_type', 'status_badge', 'reviewer', 
        'due_date', 'overdue_status', 'created_at'
    ]
    list_filter = ['status', 'review_type', 'vendor', 'due_date']
    search_fields = ['document__document_number', 'document__title', 'comments']
    readonly_fields = ['created_at', 'created_by', 'review_completed_at', 'approval_completed_at']
    date_hierarchy = 'due_date'
    
    fieldsets = (
        ('Review Information', {
            'fields': ('vendor', 'document', 'review_type', 'status')
        }),
        ('Assignment', {
            'fields': ('reviewer', 'approver', 'due_date')
        }),
        ('Review Details', {
            'fields': ('comments', 'recommendations')
        }),
        ('Completion', {
            'fields': ('review_completed_at', 'approval_completed_at'),
            'classes': ('collapse',)
        }),
        ('Audit', {
            'fields': ('created_at', 'created_by'),
            'classes': ('collapse',)
        }),
    )
    
    def status_badge(self, obj):
        colors = {
            'pending': '#ffc107',
            'in_progress': '#17a2b8',
            'approved': '#28a745',
            'rejected': '#dc3545',
            'on_hold': '#6c757d',
        }
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px;">{}</span>',
            colors.get(obj.status, '#6c757d'),
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'
    
    def overdue_status(self, obj):
        if obj.is_overdue():
            return format_html('<span style="color: red; font-weight: bold;">⚠ OVERDUE</span>')
        return format_html('<span style="color: green;">✓ On Track</span>')
    overdue_status.short_description = 'Due Status'
    
    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(DocumentApproval)
class DocumentApprovalAdmin(admin.ModelAdmin):
    list_display = [
        'document', 'approval_type', 'approver', 'approval_status', 
        'signed_at', 'ip_address'
    ]
    list_filter = ['approval_type', 'approval_status', 'vendor', 'signed_at']
    search_fields = ['document__document_number', 'approver__username', 'reason_for_signature']
    readonly_fields = ['signed_at', 'signature', 'ip_address', 'user_agent']
    date_hierarchy = 'signed_at'
    
    fieldsets = (
        ('Approval Information', {
            'fields': ('vendor', 'document', 'review', 'approval_type')
        }),
        ('Approver', {
            'fields': ('approver', 'approval_status', 'reason_for_signature', 'comments')
        }),
        ('Electronic Signature', {
            'fields': ('signature', 'signed_at')
        }),
        ('System Information', {
            'fields': ('ip_address', 'user_agent'),
            'classes': ('collapse',)
        }),
    )


@admin.register(DocumentDistribution)
class DocumentDistributionAdmin(admin.ModelAdmin):
    list_display = [
        'document', 'distributed_to', 'distribution_method', 
        'acknowledged_badge', 'distributed_at'
    ]
    list_filter = [
        'distribution_method', 'acknowledged', 
        'requires_acknowledgment', 'vendor', 'distributed_at'
    ]
    search_fields = ['document__document_number', 'distributed_to__username']
    readonly_fields = ['distributed_at', 'distributed_by', 'acknowledged_at']
    date_hierarchy = 'distributed_at'
    
    fieldsets = (
        ('Distribution', {
            'fields': ('vendor', 'document', 'distributed_to', 'distribution_method')
        }),
        ('Acknowledgment', {
            'fields': (
                'requires_acknowledgment', 'acknowledged', 
                'acknowledged_at', 'acknowledgment_signature'
            )
        }),
        ('Audit', {
            'fields': ('distributed_at', 'distributed_by'),
            'classes': ('collapse',)
        }),
    )
    
    def acknowledged_badge(self, obj):
        if obj.acknowledged:
            return format_html(
                '<span style="color: green; font-weight: bold;">✓ Acknowledged</span>'
            )
        return format_html(
            '<span style="color: orange; font-weight: bold;">⏳ Pending</span>'
        )
    acknowledged_badge.short_description = 'Status'
    
    def save_model(self, request, obj, form, change):
        if not change:
            obj.distributed_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(DocumentTraining)
class DocumentTrainingAdmin(admin.ModelAdmin):
    list_display = [
        'document', 'trainee', 'training_type', 'status_badge', 
        'completed_at', 'assessment_passed', 'expiry_date'
    ]
    list_filter = [
        'status', 'training_type', 'assessment_passed', 
        'vendor', 'assigned_at'
    ]
    search_fields = ['document__document_number', 'trainee__username', 'notes']
    readonly_fields = ['assigned_at', 'assigned_by']
    date_hierarchy = 'assigned_at'
    
    fieldsets = (
        ('Training Assignment', {
            'fields': ('vendor', 'document', 'trainee', 'training_type', 'status')
        }),
        ('Training Details', {
            'fields': ('trainer', 'training_duration_minutes', 'notes')
        }),
        ('Completion & Assessment', {
            'fields': (
                'completed_at', 'expiry_date', 
                'assessment_score', 'assessment_passed'
            )
        }),
        ('Audit', {
            'fields': ('assigned_at', 'assigned_by'),
            'classes': ('collapse',)
        }),
    )
    
    def status_badge(self, obj):
        colors = {
            'required': '#ffc107',
            'in_progress': '#17a2b8',
            'completed': '#28a745',
            'expired': '#dc3545',
        }
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px;">{}</span>',
            colors.get(obj.status, '#6c757d'),
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'
    
    def save_model(self, request, obj, form, change):
        if not change:
            obj.assigned_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(DocumentAuditLog)
class DocumentAuditLogAdmin(admin.ModelAdmin):
    list_display = [
        'document', 'action', 'user_full_name', 
        'timestamp', 'ip_address'
    ]
    list_filter = ['action', 'vendor', 'timestamp']
    search_fields = ['document__document_number', 'user_full_name', 'description']
    readonly_fields = [
        'document', 'action', 'user', 'user_full_name', 
        'description', 'old_value', 'new_value', 
        'ip_address', 'user_agent', 'timestamp'
    ]
    date_hierarchy = 'timestamp'
    
    def has_add_permission(self, request):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(DocumentReference)
class DocumentReferenceAdmin(admin.ModelAdmin):
    list_display = [
        'source_document', 'reference_type', 'referenced_document', 
        'created_at', 'created_by'
    ]
    list_filter = ['reference_type', 'vendor', 'created_at']
    search_fields = [
        'source_document__document_number', 
        'referenced_document__document_number', 
        'notes'
    ]
    readonly_fields = ['created_at', 'created_by']
    
    fieldsets = (
        ('Reference', {
            'fields': (
                'vendor', 'source_document', 
                'referenced_document', 'reference_type'
            )
        }),
        ('Details', {
            'fields': ('notes',)
        }),
        ('Audit', {
            'fields': ('created_at', 'created_by'),
            'classes': ('collapse',)
        }),
    )
    
    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)















# from django.contrib import admin
# from .models import (DocumentCategory, Document, DocumentVersion, 
#                      ElectronicSignature, DocumentAuditTrail, 
#                      DocumentTrainingRecord,
#                      ) 


# class DocumentVersionInline(admin.TabularInline):
#     model = DocumentVersion
#     # Optional: Display more fields directly in the inline
#     fields = ('version_number', 'status', 'is_effective', 'created_at', 'created_by') 
#     readonly_fields = ('status', 'is_effective', 'created_at', 'created_by')
#     extra = 0


# @admin.register(DocumentCategory)
# class DocumentCategoryAdmin(admin.ModelAdmin):
#     # FIX 1: Trailing comma for single-item tuple
#     list_display = ('name',) 
#     search_fields = ('name',)
#     list_filter = ('created_at',)


# @admin.register(Document)
# class DocumentAdmin(admin.ModelAdmin):
#     list_display = ('title', 'category', 'status', 'owner', 'review_due_date')
#     list_filter = ('category', 'status', 'owner')
#     search_fields = ('title', 'owner__username')
#     inlines = [DocumentVersionInline]
#     # Ensure audit fields are visible
#     readonly_fields = ('created_at', 'created_by', 'updated_at', 'updated_by')


# @admin.register(DocumentVersion)
# class DocumentVersionAdmin(admin.ModelAdmin):
#     list_display = ('document', 'version_number', 'status', 'is_effective', 'is_obsolete')
#     list_filter = ('status', 'is_effective', 'is_obsolete') # Enhanced filtering
#     search_fields = ('version_number', 'document__title')
#     # All version details are read-only once saved for compliance
#     readonly_fields = [f.name for f in DocumentVersion._meta.get_fields() if f.name not in ('id', 'change_summary', 'document')]
#     fieldsets = (
#         (None, {'fields': ('document', 'version_number', 'file', 'file_checksum', 'change_summary')}),
#         ('Compliance Status', {'fields': ('status', 'is_effective', 'is_obsolete', 'approved_by', 'approved_at')}),
#         ('Audit Trail', {'fields': ('created_at', 'created_by')}),
#     )


# @admin.register(ElectronicSignature)
# class ElectronicSignatureAdmin(admin.ModelAdmin):
#     list_display = ('user', 'document_version', 'action', 'reason', 'signed_at')
#     list_filter = ('action',)
#     search_fields = ('user__username', 'document_version__document__title')
#     readonly_fields = ('user', 'document_version', 'action', 'verification_data', 'signed_at', 'created_at', 'created_by')


# @admin.register(DocumentAuditTrail)
# class DocumentAuditTrailAdmin(admin.ModelAdmin):
#     list_display = ('document_version', 'action', 'performed_by', 'timestamp', 'details')
#     list_filter = ('action', 'performed_by') # Critical for auditing
#     search_fields = ('document_version__document__title', 'action')
#     readonly_fields = ('document_version', 'action', 'performed_by', 'timestamp', 'details')


# @admin.register(DocumentTrainingRecord)
# class DocumentTrainingRecordAdmin(admin.ModelAdmin):
#     list_display = ('user', 'document_version', 'created_at')
#     list_filter = ('document_version__document',)
#     search_fields = ('user__username', 'document_version__document__title')
#     readonly_fields = ('user', 'document_version', 'created_at', 'created_by')

# # -------------------------------------------------------------
# # NOTES / SECURITY
# # -------------------------------------------------------------
# # - Ensure MEDIA storage is S3 with server-side encryption and signed URLs for downloads.
# # - Replace sign_electronic_signature with an HSM-backed signing service in production.
# # - Enforce strong RBAC: e.g., only users with 'doc_control.approve_documentversion' can call approve_version.
# # - Record IP addresses and session IDs if required for audit.
