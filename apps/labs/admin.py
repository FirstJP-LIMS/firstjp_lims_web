from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from .models import (
    TestAssignment, TestResult, Equipment, 
    InstrumentLog, AuditLog,
    VendorTest, Patient, Sample, TestRequest, Department,
    # quality_control
    QCLot
)

"""
firstjplabs@gmail.com
firstjp
"""

# Register simple models
admin.site.register(Department)
admin.site.register(VendorTest)
admin.site.register(Patient)
admin.site.register(Sample)
admin.site.register(TestRequest)


@admin.register(TestResult)
class TestResultAdmin(admin.ModelAdmin):
    list_display = ['id', 'assignment', 'result_value', 'flag', 'entered_by', 'verified_at']
    # Permissions will automatically appear in user/group admin


@admin.register(QCLot)
class QCLotAdmin(admin.ModelAdmin):
    list_display = ('test', 'lot_number', 'level', 'vendor', 'is_active', 'expiry_date')
    list_filter = ('vendor', 'test', 'level', 'is_active')
    search_fields = ('lot_number', 'test__name', 'test__code')

# @admin.register(Equipment)
# class EquipmentAdmin(admin.ModelAdmin):
#     list_display = [
#         'name', 'model', 'serial_number', 'department', 
#         'status', 'supports_auto_fetch', 'api_configured'
#     ]
#     list_filter = ['status', 'department', 'supports_auto_fetch', 'vendor']
#     search_fields = ['name', 'model', 'serial_number']
#     readonly_fields = ['last_calibrated']
    
#     fieldsets = (
#         ('Basic Information', {
#             'fields': ('vendor', 'name', 'model', 'serial_number', 'department', 'status')
#         }),
#         ('API Configuration', {
#             'fields': ('api_endpoint', 'api_key', 'supports_auto_fetch'),
#             'classes': ('collapse',)
#         }),
#         ('Maintenance', {
#             'fields': ('last_calibrated',),
#         }),
#     )
    
#     def api_configured(self, obj):
#         if obj.api_endpoint and obj.api_key:
#             return format_html('<span style="color: green;">✓ Configured</span>')
#         return format_html('<span style="color: red;">✗ Not Configured</span>')
#     api_configured.short_description = 'API Status'


# class TestResultInline(admin.StackedInline):
#     model = TestResult
#     extra = 0
#     readonly_fields = ['entered_at', 'verified_at', 'version']
#     fields = [
#         'result_value', 'units', 'reference_range', 'flag',
#         'data_source', 'remarks', 
#         'entered_by', 'entered_at',
#         'verified_by', 'verified_at',
#         'released', 'released_at'
#     ]
    
#     def has_delete_permission(self, request, obj=None):
#         # Prevent deletion of verified results
#         if obj and obj.verified_at:
#             return False
#         return super().has_delete_permission(request, obj)


# @admin.register(TestAssignment)
# class TestAssignmentAdmin(admin.ModelAdmin):
#     list_display = [
#         'id', 'request_link', 'patient_name', 'test_name', 
#         'status_badge', 'instrument', 'priority_badge',
#         'created_at', 'quick_actions'  # ✅ RENAMED from 'actions'
#     ]
#     list_filter = [
#         'status', 'department', 'instrument', 
#         'request__priority', 'created_at', 'vendor'
#     ]
#     search_fields = [
#         'request__request_id', 
#         'request__patient__patient_id',
#         'request__patient__first_name',
#         'request__patient__last_name',
#         'lab_test__name',
#         'lab_test__code',
#         'sample__sample_id'
#     ]
#     readonly_fields = [
#         'created_at', 'updated_at', 'queued_at', 
#         'analyzed_at', 'verified_at', 'external_id',
#         'retry_count', 'last_sync_attempt'
#     ]
#     inlines = [TestResultInline]
    
#     fieldsets = (
#         ('Assignment Details', {
#             'fields': (
#                 'vendor', 'request', 'lab_test', 'sample', 
#                 'department', 'instrument', 'assigned_to'
#             )
#         }),
#         ('Status & Tracking', {
#             'fields': (
#                 'status', 'external_id', 'retry_count',
#                 'created_at', 'queued_at', 'analyzed_at', 
#                 'verified_at', 'last_sync_attempt', 'updated_at'
#             )
#         }),
#     )
    
#     # ✅ Django admin actions (bulk actions)
#     actions = [
#         'mark_as_queued', 
#         'mark_as_analyzed',
#         'send_to_instruments'
#     ]
    
#     def request_link(self, obj):
#         url = reverse('admin:laboratory_testrequest_change', args=[obj.request.id])
#         return format_html('<a href="{}">{}</a>', url, obj.request.request_id)
#     request_link.short_description = 'Request ID'
    
#     def patient_name(self, obj):
#         return f"{obj.request.patient.first_name} {obj.request.patient.last_name}"
#     patient_name.short_description = 'Patient'
    
#     def test_name(self, obj):
#         return f"{obj.lab_test.name} ({obj.lab_test.code})"
#     test_name.short_description = 'Test'
    
#     def status_badge(self, obj):
#         colors = {
#             'P': '#ffc107', 'Q': '#0dcaf0', 'I': '#6c757d',
#             'A': '#0d6efd', 'V': '#198754', 'R': '#dc3545'
#         }
#         color = colors.get(obj.status, '#6c757d')
#         return format_html(
#             '<span style="background: {}; color: white; padding: 3px 8px; '
#             'border-radius: 3px; font-size: 11px;">{}</span>',
#             color, obj.get_status_display()
#         )
#     status_badge.short_description = 'Status'
    
#     def priority_badge(self, obj):
#         colors = {
#             'stat': '#dc3545', 'urgent': '#fd7e14', 'routine': '#0dcaf0'
#         }
#         priority = obj.request.priority.lower()
#         color = colors.get(priority, '#0dcaf0')
#         return format_html(
#             '<span style="background: {}; color: white; padding: 3px 8px; '
#             'border-radius: 3px; font-size: 11px;">{}</span>',
#             color, priority.upper()
#         )
#     priority_badge.short_description = 'Priority'
    
#     # ✅ RENAMED METHOD: actions → quick_actions
#     def quick_actions(self, obj):
#         """Display quick action buttons in list view"""
#         buttons = []
        
#         if obj.can_send_to_instrument():
#             buttons.append(
#                 format_html(
#                     '<a class="button" style="padding: 5px 10px; '
#                     'background: #0d6efd; color: white; text-decoration: none; '
#                     'border-radius: 3px; font-size: 11px;" '
#                     'href="{}">Send to Instrument</a>',
#                     reverse('laboratory:send_to_instrument', args=[obj.id])
#                 )
#             )
        
#         if obj.status in ['Q', 'I'] and obj.external_id:
#             buttons.append(
#                 format_html(
#                     '<a class="button" style="padding: 5px 10px; '
#                     'background: #198754; color: white; text-decoration: none; '
#                     'border-radius: 3px; font-size: 11px;" '
#                     'href="{}">Fetch Result</a>',
#                     reverse('laboratory:fetch_result_from_instrument', args=[obj.id])
#                 )
#             )
        
#         return format_html(' '.join(buttons)) if buttons else '—'
#     quick_actions.short_description = 'Quick Actions'
    
#     # ===== Admin Bulk Actions =====
#     def mark_as_queued(self, request, queryset):
#         """Bulk action: Mark selected assignments as queued"""
#         count = 0
#         for assignment in queryset.filter(status='P'):
#             assignment.mark_queued()
#             count += 1
#         self.message_user(request, f'{count} assignment(s) marked as queued.')
#     mark_as_queued.short_description = 'Mark selected as Queued'
    
#     def mark_as_analyzed(self, request, queryset):
#         """Bulk action: Mark selected assignments as analyzed"""
#         count = 0
#         for assignment in queryset.filter(status__in=['Q', 'I']):
#             assignment.mark_analyzed()
#             count += 1
#         self.message_user(request, f'{count} assignment(s) marked as analyzed.')
#     mark_as_analyzed.short_description = 'Mark selected as Analyzed'
    
#     def send_to_instruments(self, request, queryset):
#         """Bulk action: Send selected assignments to their instruments"""
#         from .services import send_assignment_to_instrument, InstrumentAPIError
#         success = 0
#         failed = 0
        
#         for assignment in queryset.filter(status='P'):
#             if assignment.can_send_to_instrument():
#                 try:
#                     send_assignment_to_instrument(assignment.id)
#                     success += 1
#                 except InstrumentAPIError:
#                     failed += 1
        
#         self.message_user(
#             request, 
#             f'Sent {success} assignment(s) to instruments. {failed} failed.'
#         )
#     send_to_instruments.short_description = 'Send selected to instruments'


# @admin.register(TestResult)
# class TestResultAdmin(admin.ModelAdmin):
#     list_display = [
#         'assignment_link', 'result_value', 'units', 
#         'flag_badge', 'data_source', 'verified_status',
#         'entered_at'
#     ]
#     list_filter = [
#         'flag', 'data_source', 'released', 
#         'verified_at', 'entered_at'
#     ]
#     search_fields = [
#         'assignment__request__request_id',
#         'assignment__request__patient__patient_id',
#         'result_value'
#     ]
#     readonly_fields = [
#         'entered_at', 'verified_at', 'released_at', 
#         'version', 'previous_value'
#     ]
    
#     fieldsets = (
#         ('Result Data', {
#             'fields': (
#                 'assignment', 'result_value', 'units', 
#                 'reference_range', 'flag'
#             )
#         }),
#         ('Additional Information', {
#             'fields': ('remarks', 'interpretation', 'data_source')
#         }),
#         ('Workflow', {
#             'fields': (
#                 'entered_by', 'entered_at',
#                 'verified_by', 'verified_at',
#                 'released', 'released_at'
#             )
#         }),
#         ('Version Control', {
#             'fields': ('version', 'previous_value'),
#             'classes': ('collapse',)
#         }),
#     )
    
#     def assignment_link(self, obj):
#         url = reverse('admin:laboratory_testassignment_change', args=[obj.assignment.id])
#         return format_html(
#             '<a href="{}">{}</a>', 
#             url, 
#             obj.assignment.request.request_id
#         )
#     assignment_link.short_description = 'Assignment'
    
#     def flag_badge(self, obj):
#         colors = {
#             'N': '#198754', 'H': '#dc3545', 'L': '#ffc107',
#             'A': '#6c757d', 'C': '#dc3545'
#         }
#         color = colors.get(obj.flag, '#6c757d')
#         return format_html(
#             '<span style="background: {}; color: white; padding: 3px 8px; '
#             'border-radius: 3px; font-size: 11px;">{}</span>',
#             color, obj.get_flag_display()
#         )
#     flag_badge.short_description = 'Flag'
    
#     def verified_status(self, obj):
#         if obj.verified_at:
#             return format_html('<span style="color: green;">✓ Verified</span>')
#         return format_html('<span style="color: orange;">⏳ Pending</span>')
#     verified_status.short_description = 'Verification'
    
#     def has_delete_permission(self, request, obj=None):
#         # Prevent deletion of verified or released results
#         if obj and (obj.verified_at or obj.released):
#             return False
#         return super().has_delete_permission(request, obj)


# @admin.register(InstrumentLog)
# class InstrumentLogAdmin(admin.ModelAdmin):
#     list_display = [
#         'created_at', 'log_type_badge', 'assignment_link', 
#         'instrument', 'response_code', 'has_error'
#     ]
#     list_filter = ['log_type', 'instrument', 'created_at']
#     search_fields = [
#         'assignment__request__request_id',
#         'error_message'
#     ]
#     readonly_fields = ['created_at', 'payload']
    
#     fieldsets = (
#         ('Log Information', {
#             'fields': (
#                 'assignment', 'instrument', 'log_type', 
#                 'created_at'
#             )
#         }),
#         ('Communication Data', {
#             'fields': ('payload', 'response_code', 'error_message')
#         }),
#     )
    
#     def assignment_link(self, obj):
#         url = reverse('admin:laboratory_testassignment_change', args=[obj.assignment.id])
#         return format_html('<a href="{}">{}</a>', url, obj.assignment.request.request_id)
#     assignment_link.short_description = 'Assignment'
    
#     def log_type_badge(self, obj):
#         colors = {
#             'send': '#0d6efd', 'receive': '#198754', 'error': '#dc3545'
#         }
#         color = colors.get(obj.log_type, '#6c757d')
#         return format_html(
#             '<span style="background: {}; color: white; padding: 3px 8px; '
#             'border-radius: 3px; font-size: 11px;">{}</span>',
#             color, obj.get_log_type_display()
#         )
#     log_type_badge.short_description = 'Type'
    
#     def has_error(self, obj):
#         if obj.error_message:
#             return format_html('<span style="color: red;">✗ Error</span>')
#         return format_html('<span style="color: green;">✓ OK</span>')
#     has_error.short_description = 'Status'
    
#     def has_add_permission(self, request):
#         return False  # Logs are auto-generated
    
#     def has_change_permission(self, request, obj=None):
#         return False  # Logs are immutable


# @admin.register(AuditLog)
# class AuditLogAdmin(admin.ModelAdmin):
#     list_display = ['created_at', 'user', 'action_preview', 'ip_address']
#     list_filter = ['vendor', 'created_at', 'user']
#     search_fields = ['action', 'user__username', 'ip_address']
#     readonly_fields = ['created_at', 'action']
    
#     def action_preview(self, obj):
#         return obj.action[:100] + '...' if len(obj.action) > 100 else obj.action
#     action_preview.short_description = 'Action'
    
#     def has_add_permission(self, request):
#         return False
    
#     def has_change_permission(self, request, obj=None):
#         return False
    
#     def has_delete_permission(self, request, obj=None):
#         return request.user.is_superuser  # Only superusers can delete audit logs



