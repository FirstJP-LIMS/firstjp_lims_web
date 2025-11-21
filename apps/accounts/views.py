# app/accounts/views.py
from django.shortcuts import render, redirect, get_object_or_404, Http404
from django.views.generic import TemplateView
from apps.tenants.models import Vendor
from .forms import RegistrationForm, TenantAuthenticationForm, VendorProfile, VendorProfileForm
from django.urls import reverse, reverse_lazy
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from .forms import TenantAuthenticationForm
from django.contrib.auth.decorators import user_passes_test, login_required
from django.shortcuts import render, redirect


# ----------------------------------
# Tenant-aware auth. 
# ----------------------------------

# Define allowed roles for public registration on the vendor subdomain
ALLOWED_PUBLIC_ROLES = ['lab_staff', 'clinician', 'patient']

def tenant_register_by_role(request, role_name):
    """
    Handles registration for lab_staff, clinician, or patient, scoped to the current tenant.
    The role_name is passed via the URL patterns.
    """
    tenant = getattr(request, 'tenant', None)
    
    # 1. Input Validation: Check if the role is valid for public registration
    if role_name not in ALLOWED_PUBLIC_ROLES:
        # Invalid role in URL should be handled gracefully
        raise Http404("Invalid registration path or user role.")
    
    # Check if tenant exists
    if not tenant:
        messages.error(request, "Cannot register. Tenant could not be resolved from the domain. Contact support.")
        form = RegistrationForm()
    
    # Get the human-readable role name for the template context
    role_display_name = role_name.replace('_', ' ').title()

    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        
        if form.is_valid():
            if not tenant:
                 messages.error(request, "Cannot register. Tenant could not be resolved after POST.")
                 return render(request, 'registration/register.html', {'form': form, 'lab_name': 'Error'})
                 
            # 2. Save the user with the correct tenant and role
            form.save(vendor=tenant, role=role_name)
            messages.success(request, f"{role_display_name} account created successfully. You can now log in.")
            return redirect(reverse('login'))
    else:
        form = RegistrationForm()

    # Pass context to the template
    context = {
        'form': form,
        'tenant': tenant,
        'lab_name': tenant.name if tenant else "LIMS Platform",
        'role_name': role_display_name, # e.g., 'Lab Staff'
        'role_key': role_name, # e.g., 'lab_staff'
    }
    return render(request, 'registration/register.html', context)


# Admin-only vendor-admin creation
def is_platform_admin(user):
    return user.is_authenticated and user.is_platform_admin

@user_passes_test(is_platform_admin)
def create_vendor_admin(request, vendor_id):
    vendor = get_object_or_404(Vendor, internal_id=vendor_id)
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            form.save(vendor=vendor, role='vendor_admin')
            return redirect('admin:tenants_vendor_change', vendor.internal_id)
    else:
        form = RegistrationForm()
    return render(request, 'registration/create_vendor_admin.html', {'form': form, 'vendor': vendor})


def tenant_login(request):
    vendorInfo = Vendor.objects.prefetch_related('name')
    tenant = getattr(request, 'tenant', None)    
    if request.method == 'POST':
        form = TenantAuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()

            # 1️⃣ Platform Admin: global access
            if getattr(user, 'is_platform_admin', False):
                login(request, user)
                messages.success(request, f"Welcome back, {user.email}")
                return redirect(reverse('dashboard'))

            # 2️⃣ Tenant validation
            if not tenant:
                messages.error(request, "No tenant could be resolved. Access denied.")
                return redirect(reverse('no_tenant'))

            if not user.vendor or user.vendor.internal_id != tenant.internal_id:
                messages.error(request, "This account does not belong to this tenant.")
                return redirect(reverse('login'))

            # 3️⃣ Tenant-bound login successful
            login(request, user)
            messages.success(request, f"Welcome, {user.email}")

            # 4️⃣ Role-based redirection
            if user.role in ['vendor_admin', 'lab_staff']:
                return redirect(reverse('labs:vendor_dashboard'))
            elif user.role == 'patient':
                return redirect(reverse('labs:patient_dashboard'))
            elif user.role == 'clinician':
                return redirect(reverse('labs:clinician_dashboard'))
            else:
                # fallback route for unknown roles
                return redirect(reverse('login'))
    else:
        form = TenantAuthenticationForm(request)

    context = {
        'form': form,
        'tenant': tenant,
        'vendorInfo': vendorInfo,
    }
    return render(request, 'platform/pages/login.html', context)

def tenant_logout(request):
    logout(request)
    messages.info(request, "You have been logged out successfully.")
    return redirect(reverse_lazy('login'))

"""
    Tasks to complete:
    Password Resetting...
"""

# ------------------------------
# Tenant-Aware Auth. ends here
# ------------------------------

# ----------------------------------
# Admin Dashboard to be worked on..
# ----------------------------------
class DashboardView(TemplateView):
    template_name = 'admin_ui/dashboard.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['tenant'] = getattr(self.request, 'tenant', None)
        return ctx


# ------------------------------
# VENDOR OPERATIONS
# ------------------------------
# profile management 
@login_required
def vendor_profile(request):
    vendor = request.user.vendor

    # Ensure vendor has a profile
    profile, created = VendorProfile.objects.get_or_create(vendor=vendor)

    if request.method == "POST":
        form = VendorProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated successfully.")
            return redirect("account:laboratory_profile")
    else:
        form = VendorProfileForm(instance=profile)

    context = {
        "vendor": vendor,
        "user": request.user,   # contains email (non-editable)
        "form": form,
        "profile": profile,
    }
    return render(request, "laboratory/account_mgt/lab_profile.html", context)


# ------------------------------
# VENDOR OPERATIONS
# ------------------------------
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
from apps.labs.models import Equipment, Department, AuditLog


@login_required
def equipment_list(request):
    """List all equipment for current vendor"""
    equipment = Equipment.objects.filter(
        vendor=request.user.vendor
    ).select_related('department').order_by('-status', 'name')
    
    context = {
        'equipment_list': equipment,
        'active_count': equipment.filter(status='active').count(),
        'maintenance_count': equipment.filter(status='maintenance').count(),
    }
    
    return render(request, 'laboratory/equipment/equipment_list.html', context)


# app_name/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.db import transaction
# from .models import Equipment, Department, AuditLog
from .forms import EquipmentForm


@login_required
@require_http_methods(["GET", "POST"])
def equipment_create(request):
    form = EquipmentForm(request.POST or None, vendor=request.user.vendor)

    if request.method == "POST":
        if form.is_valid():
            try:
                with transaction.atomic():
                    equipment = form.save(commit=False)
                    equipment.vendor = request.user.vendor
                    equipment.status = "active"
                    equipment.save()

                    # Log audit
                    AuditLog.objects.create(
                        vendor=request.user.vendor,
                        user=request.user,
                        action=f"Created equipment: {equipment.name} ({equipment.serial_number})",
                        ip_address=request.META.get("REMOTE_ADDR")
                    )

                messages.success(request, f"Equipment '{equipment.name}' created successfully.")
                return redirect("equipment_detail", equipment_id=equipment.id)

            except Exception as e:
                messages.error(request, f"Error creating equipment: {str(e)}")

        else:
            messages.error(request, "Please correct the errors below.")

    return render(request, "laboratory/equipment/equipment_form.html", {
        "form": form,
        "action": "Create"
    })


@login_required
def equipment_detail(request, equipment_id):
    """View equipment details and recent assignments"""
    equipment = get_object_or_404(
        Equipment.objects.select_related('department'),
        id=equipment_id,
        vendor=request.user.vendor
    )
    
    # Get recent assignments using this equipment
    recent_assignments = equipment.assignments.select_related(
        'request__patient',
        'lab_test'
    ).order_by('-created_at')[:10]
    
    # Get basic stats
    total_assignments = equipment.assignments.count()
    pending_assignments = equipment.assignments.filter(status='P').count()
    queued_assignments = equipment.assignments.filter(status='Q').count()
    
    context = {
        'equipment': equipment,
        'recent_assignments': recent_assignments,
        'total_assignments': total_assignments,
        'pending_assignments': pending_assignments,
        'queued_assignments': queued_assignments,
        'is_configured': bool(equipment.api_endpoint),
    }
    
    return render(request, 'laboratory/equipment/equipment_detail.html', context)


@login_required
@require_http_methods(["GET", "POST"])
def equipment_update(request, equipment_id):
    """Update equipment configuration"""
    equipment = get_object_or_404(
        Equipment,
        id=equipment_id,
        vendor=request.user.vendor
    )
    
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        model = request.POST.get("model", "").strip()
        department_id = request.POST.get("department")
        api_endpoint = request.POST.get("api_endpoint", "").strip()
        api_key = request.POST.get("api_key", "").strip()
        supports_auto_fetch = request.POST.get("supports_auto_fetch") == "on"
        status = request.POST.get("status")
        
        # Validation
        if not all([name, model, department_id, status]):
            messages.error(request, "Please fill in all required fields.")
            return redirect('equipment_update', equipment_id=equipment.id)
        
        try:
            department = Department.objects.get(
                id=department_id,
                vendor=request.user.vendor
            )
            
            # Track what changed
            changes = []
            if equipment.name != name:
                changes.append(f"name: '{equipment.name}' → '{name}'")
            if equipment.api_endpoint != api_endpoint:
                changes.append("API endpoint updated")
            if equipment.status != status:
                changes.append(f"status: {equipment.get_status_display()} → {dict(Equipment.EQUIPMENT_STATUS)[status]}")
            
            # Update equipment
            equipment.name = name
            equipment.model = model
            equipment.department = department
            equipment.api_endpoint = api_endpoint
            equipment.supports_auto_fetch = supports_auto_fetch
            equipment.status = status
            
            # Only update API key if provided (don't overwrite with blank)
            if api_key:
                equipment.api_key = api_key
            
            equipment.save()
            
            # Log the changes
            if changes:
                AuditLog.objects.create(
                    vendor=request.user.vendor,
                    user=request.user,
                    action=f"Updated equipment {equipment.name}: {', '.join(changes)}",
                    ip_address=request.META.get('REMOTE_ADDR')
                )
            
            messages.success(request, "Equipment updated successfully.")
            return redirect('equipment_detail', equipment_id=equipment.id)
            
        except Department.DoesNotExist:
            messages.error(request, "Invalid department selected.")
        except Exception as e:
            messages.error(request, f"Error updating equipment: {str(e)}")
    
    # GET request
    departments = Department.objects.filter(vendor=request.user.vendor)
    
    return render(request, 'laboratory/equipment/equipment_form.html', {
        'equipment': equipment,
        'departments': departments,
        'action': 'Update'
    })


@login_required
@require_http_methods(["POST"])
def equipment_calibrate(request, equipment_id):
    """Mark equipment as calibrated"""
    equipment = get_object_or_404(
        Equipment,
        id=equipment_id,
        vendor=request.user.vendor
    )
    
    from django.utils import timezone
    
    equipment.last_calibrated = timezone.now().date()
    equipment.save(update_fields=['last_calibrated'])
    
    AuditLog.objects.create(
        vendor=request.user.vendor,
        user=request.user,
        action=f"Calibrated equipment: {equipment.name}",
        ip_address=request.META.get('REMOTE_ADDR')
    )
    
    messages.success(request, f"Equipment '{equipment.name}' marked as calibrated.")
    return redirect('equipment_detail', equipment_id=equipment.id)


@login_required
@require_http_methods(["POST"])
def equipment_deactivate(request, equipment_id):
    """Deactivate or reactivate equipment"""
    equipment = get_object_or_404(
        Equipment,
        id=equipment_id,
        vendor=request.user.vendor
    )
    
    new_status = 'inactive' if equipment.status == 'active' else 'active'
    equipment.status = new_status
    equipment.save(update_fields=['status'])
    
    AuditLog.objects.create(
        vendor=request.user.vendor,
        user=request.user,
        action=f"Changed equipment {equipment.name} status to {new_status}",
        ip_address=request.META.get('REMOTE_ADDR')
    )
    
    messages.success(request, f"Equipment status changed to {equipment.get_status_display()}.")
    return redirect('equipment_detail', equipment_id=equipment.id)


@login_required
def equipment_test_connection(request, equipment_id):
    """Test API connection to equipment (AJAX endpoint)"""
    equipment = get_object_or_404(
        Equipment,
        id=equipment_id,
        vendor=request.user.vendor
    )
    
    if not equipment.api_endpoint:
        return JsonResponse({
            'success': False,
            'message': 'No API endpoint configured'
        })
    
    # Import your instrument service
    from .services import InstrumentService
    
    try:
        service = InstrumentService(equipment)
        status = service.check_instrument_status()
        
        return JsonResponse({
            'success': status.get('is_online', False),
            'message': status.get('message', 'Connection test completed'),
            'details': status
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Connection failed: {str(e)}'
        })