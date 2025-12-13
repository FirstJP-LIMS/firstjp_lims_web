# from django.contrib import admin
# from . models import (
#     ClinicianPatientRelationship,
#     ClinicianProfile
# )

# # Register your models here.
# admin.site.register(ClinicianProfile)
# admin.site.register(ClinicianPatientRelationship)


from django.contrib import admin
from .models import ClinicianProfile, ClinicianPatientRelationship

@admin.register(ClinicianProfile)
class ClinicianProfileAdmin(admin.ModelAdmin):
    list_display = [
        'get_clinician_name',
        'license_number',
        'specialization',
        'organization',
        'is_verified',
        'is_active',
        'total_orders_placed',
        'created_at'
    ]
    
    list_filter = [
        'is_verified',
        'is_active',
        'specialization',
        'created_at'
    ]
    
    search_fields = [
        'user__email',
        'user__first_name',
        'user__last_name',
        'license_number',
        'organization'
    ]
    
    readonly_fields = [
        'created_at',
        'updated_at',
        'total_orders_placed',
        'last_order_date'
    ]
    
    fieldsets = (
        ('User Information', {
            'fields': ('user',)
        }),
        ('Professional Details', {
            'fields': (
                'license_number',
                'specialization',
                'organization',
                'department',
                'qualifications',
            )
        }),
        ('Preferences', {
            'fields': (
                'default_test_priority',
                'enable_critical_alerts',
                'preferred_contact_method',
            )
        }),
        ('Verification & Status', {
            'fields': (
                'is_verified',
                'verification_notes',
                'is_active',
            )
        }),
        ('Statistics', {
            'fields': (
                'total_orders_placed',
                'last_order_date',
            ),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': (
                'created_at',
                'updated_at',
            ),
            'classes': ('collapse',)
        }),
    )
    
    def get_clinician_name(self, obj):
        """Display clinician's full name."""
        return obj.user.get_full_name() or obj.user.email
    get_clinician_name.short_description = 'Clinician Name'
    get_clinician_name.admin_order_field = 'user__first_name'
    
    actions = ['verify_clinicians', 'deactivate_clinicians']
    
    def verify_clinicians(self, request, queryset):
        """Bulk verify clinicians."""
        updated = queryset.update(is_verified=True)
        self.message_user(request, f'{updated} clinician(s) verified successfully.')
    verify_clinicians.short_description = 'Verify selected clinicians'
    
    def deactivate_clinicians(self, request, queryset):
        """Bulk deactivate clinicians."""
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} clinician(s) deactivated.')
    deactivate_clinicians.short_description = 'Deactivate selected clinicians'


@admin.register(ClinicianPatientRelationship)
class ClinicianPatientRelationshipAdmin(admin.ModelAdmin):
    list_display = [
        'get_clinician_name',
        'get_patient_id',
        'relationship_type',
        'is_active',
        'established_date',
        'last_interaction'
    ]
    
    list_filter = [
        'relationship_type',
        'is_active',
        'established_date'
    ]
    
    search_fields = [
        'clinician__email',
        'clinician__first_name',
        'clinician__last_name',
        'patient__patient_id',
        'patient__first_name',
        'patient__last_name'
    ]
    
    readonly_fields = [
        'established_date',
        'last_interaction',
        'established_via'
    ]
    
    def get_clinician_name(self, obj):
        return obj.clinician.get_full_name() or obj.clinician.email
    get_clinician_name.short_description = 'Clinician'
    
    def get_patient_id(self, obj):
        return obj.patient.patient_id
    get_patient_id.short_description = 'Patient ID'