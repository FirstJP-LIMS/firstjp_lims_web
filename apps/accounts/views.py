# app/accounts/views.py
from django.shortcuts import render, redirect, get_object_or_404, Http404
from django.views.generic import TemplateView
from apps.tenants.models import Vendor
from .forms import RegistrationForm, TenantAuthenticationForm, VendorProfile, VendorProfileForm, TenantPasswordResetForm
from django.urls import reverse, reverse_lazy
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import user_passes_test, login_required
from django.shortcuts import render, redirect
from django_ratelimit.decorators import ratelimit


# role groups

LEARN_ALLOWED = ['learner', 'facilitator']
TENANT_ALLOWED = ['vendor_admin', 'lab_staff', 'patient', 'clinician']

def tenant_register_by_role(request, role_name):
    """
        Handles registration for tenant-scoped roles (lab_staff, clinician, patient, vendor_admin), scoped to the current tenant.
    """
    tenant = getattr(request, 'tenant', None)

    if role_name not in TENANT_ALLOWED:
        raise Http404("Invalid registration path or user role.")

    if not tenant:
        messages.error(request, "Tenant could not be resolved.")
        return redirect('account:login')

    if request.method == 'POST':
        form = RegistrationForm(
            request.POST,
            vendor=tenant,
            forced_role=role_name,
            is_learning_portal=False
        )
        if form.is_valid():
            user = form.save(vendor=tenant) # save data

            # Customize success message for patients
            if role_name == 'patient':
                messages.success(
                    request,
                    f"Welcome! Your patient account has been created for {tenant.name}. "
                    f"Please check your email to verify your account."
                )
            else:
                messages.success(
                    request,
                    f"{role_name.replace('_',' ').title()} account created for {tenant.name}."
                )
            
            return redirect(reverse('account:login'))
    else:
        form = RegistrationForm(
            vendor=tenant,
            forced_role=role_name,
            is_learning_portal=False
        )

    return render(request, 'authentication/register.html', {
        'form': form,
        'tenant': tenant,
        'role_name': role_name.replace('_',' ').title(),
    })


def learn_register(request, role_name):
    """
    Registration entry-point for learn.medvuno.com; only learner/facilitator allowed.
    """

    if not getattr(request, 'is_learning_portal', False):
        raise Http404("Not found.")

    if role_name not in LEARN_ALLOWED:
        raise Http404("Invalid registration role.")

    if request.method == 'POST':
        form = RegistrationForm(
            request.POST,
            vendor=None,
            forced_role=role_name,
            is_learning_portal=True
        )
        if form.is_valid():
            form.save()
            messages.success(request, f"{role_name.title()} account created.")
            return redirect(reverse('account:login'))
    else:
        form = RegistrationForm(
            vendor=None,
            forced_role=role_name,
            is_learning_portal=True
        )

    return render(request, 'authentication/register.html', {
        'form': form,
        'role_name': role_name.title(),
    })


@ratelimit(key='ip', rate='5/m', method='POST')
def tenant_login(request):
    tenant = getattr(request, 'tenant', None)
    is_learning = getattr(request, 'is_learning_portal', False)

    if request.method == 'POST':
        form = TenantAuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()

            # 1️⃣ Learning portal login
            if is_learning:
                # Only learner/facilitator allowed, vendor must be None
                if user.vendor is not None or user.role not in LEARN_ALLOWED:
                    messages.error(request, "This account cannot access the learning portal.")
                    return redirect(reverse('account:login'))

                login(request, user)
                messages.success(request, f"Welcome, {user.first_name or user.email}")
                # return redirect(reverse('learn:index'))  # create a learn dashboard route
                if user.role == "learner":
                    return redirect(reverse('learn:index'))  # create a learn dashboard route
                elif user.role == "facilitator":
                    return redirect(reverse('learn:facilitator_dashboard'))  # create a learn dashboard route

            # 2️⃣ Platform Admin: global access
            if getattr(user, 'is_platform_admin', False):
                login(request, user)
                # messages.success(request, f"Welcome back, {user.first_name}")
                return redirect(reverse('dashboard'))

            # 3️⃣ Tenant validation (vendor sites)
            if not tenant:
                messages.error(request, "No tenant could be resolved. Access denied.")
                return redirect(reverse('no_tenant'))

            if not user.vendor or user.vendor.internal_id != tenant.internal_id:
                messages.error(request, "This account does not belong to this tenant.")
                return redirect(reverse('account:login'))

            # Reject learning roles for tenant domains
            if user.role not in TENANT_ALLOWED:
                messages.error(request, "This account role cannot access this tenant.")
                return redirect(reverse('account:login'))

            login(request, user)
            messages.success(request, f"Welcome, {user.email}")

            # role routing
            if user.role in ['vendor_admin', 'lab_staff']:
                return redirect(reverse('labs:vendor_dashboard'))
            elif user.role == 'patient':
                return redirect(reverse('patient:patient_dashboard'))
            elif user.role == 'clinician':
                return redirect(reverse('clinician:clinician_dashboard'))
            else:
                return redirect(reverse('account:login'))
    else:
        form = TenantAuthenticationForm(request)

    context = {
        'form': form,
        'tenant': tenant
    }
    return render(request, 'authentication/login.html', context)


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


def tenant_logout(request):
    logout(request)
    messages.info(request, "You have been logged out successfully.")
    return redirect(reverse_lazy('account:login'))


"""
    Tasks to complete:
    Password Resetting...
"""
# apps/accounts/views.py
from django.contrib.auth import views as auth_views

@ratelimit(key='ip', rate='3/h', method='POST')  # 3 password resets per hour
class TenantPasswordResetView(auth_views.PasswordResetView):
    """
    Custom password reset view that injects tenant into the form.
    """
    template_name = 'registration/password_reset_form.html'
    email_template_name = 'registration/password_reset_email.html'
    subject_template_name = 'registration/password_reset_subject.txt'
    form_class = TenantPasswordResetForm
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['tenant'] = getattr(self.request, 'tenant', None)
        return kwargs
    
    def form_valid(self, form):
        """
        Add extra context for better user experience.
        """
        tenant = getattr(self.request, 'tenant', None)
        if tenant:
            messages.info(
                self.request,
                f"If your email is registered with {tenant.name}, you'll receive reset instructions."
            )
        return super().form_valid(form)

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
            return redirect('account:equipment_update', equipment_id=equipment.id)
        
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
            return redirect('account:equipment_detail', equipment_id=equipment.id)
            
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
    return redirect('account:equipment_detail', equipment_id=equipment.id)


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
    return redirect('account:equipment_detail', equipment_id=equipment.id)


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
    from app.labs.services import InstrumentService
    
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
    





"""
User Management Views for Vendor Admins
Place in: users/views.py or laboratory/views_users.py
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods, require_POST
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model
from functools import wraps
import logging

User = get_user_model()
logger = logging.getLogger(__name__)


def vendor_admin_required(view_func):
    """Decorator to ensure only vendor admins can access user management"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, 'Please log in to access this page.')
            return redirect('login')
        
        if not hasattr(request.user, 'vendor') or not request.user.vendor:
            messages.error(request, 'You must be associated with a laboratory.')
            return redirect('dashboard')
        
        if not request.user.is_vendor_admin:
            messages.error(request, 'Access denied. Only laboratory administrators can manage users.')
            return redirect('dashboard')
        
        return view_func(request, *args, **kwargs)
    
    return wrapper


# ===== USER LIST =====
@login_required
@vendor_admin_required
def user_list(request):
    """
    Display all users belonging to the vendor's laboratory.
    With search, filter, and pagination.
    """
    vendor = request.user.vendor
    
    # Base queryset - all users in this vendor
    users = User.objects.filter(vendor=vendor).exclude(
        id=request.user.id  # Exclude current user from list
    ).select_related('vendor').order_by('-date_joined')
    
    # Search
    search_query = request.GET.get('search', '')
    if search_query:
        users = users.filter(
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(contact_number__icontains=search_query)
        )
    
    # Filter by role
    role_filter = request.GET.get('role', '')
    if role_filter:
        users = users.filter(role=role_filter)
    
    # Filter by active status
    status_filter = request.GET.get('status', '')
    if status_filter == 'active':
        users = users.filter(is_active=True)
    elif status_filter == 'inactive':
        users = users.filter(is_active=False)
    
    # Statistics
    stats = {
        'total': User.objects.filter(vendor=vendor).count(),
        'active': User.objects.filter(vendor=vendor, is_active=True).count(),
        'inactive': User.objects.filter(vendor=vendor, is_active=False).count(),
        'by_role': User.objects.filter(vendor=vendor).values('role').annotate(
            count=Count('id')
        ).order_by('-count')
    }
    
    # Pagination
    paginator = Paginator(users, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    # Available roles (excluding platform_admin)
    available_roles = [
        choice for choice in User.ROLE_CHOICES 
        if choice[0] != 'platform_admin'
    ]
    
    context = {
        'page_obj': page_obj,
        'stats': stats,
        'search_query': search_query,
        'role_filter': role_filter,
        'status_filter': status_filter,
        'available_roles': available_roles,
    }
    
    return render(request, 'users/user_list.html', context)


# ===== USER DETAIL =====
@login_required
@vendor_admin_required
def user_detail(request, user_id):
    """
    Display detailed information about a specific user.
    Shows activity, permissions, and recent actions.
    """
    vendor = request.user.vendor
    user = get_object_or_404(
        User.objects.select_related('vendor'),
        id=user_id,
        vendor=vendor
    )
    
    # Get user's recent activity (if you have audit logs)
    try:
        from laboratory.models import AuditLog
        recent_activity = AuditLog.objects.filter(
            user=user,
            vendor=vendor
        ).order_by('-created_at')[:10]
    except ImportError:
        recent_activity = []
    
    # Get results entered/verified by this user
    try:
        from laboratory.models import TestResult
        
        results_entered = TestResult.objects.filter(
            entered_by=user,
            assignment__vendor=vendor
        ).count()
        
        results_verified = TestResult.objects.filter(
            verified_by=user,
            assignment__vendor=vendor
        ).count()
        
        results_released = TestResult.objects.filter(
            released_by=user,
            assignment__vendor=vendor
        ).count()
    except ImportError:
        results_entered = results_verified = results_released = 0
    
    context = {
        'profile_user': user,  # Named 'profile_user' to avoid confusion with request.user
        'recent_activity': recent_activity,
        'results_entered': results_entered,
        'results_verified': results_verified,
        'results_released': results_released,
        'permissions': user.get_permissions_summary(),
    }
    
    return render(request, 'users/user_detail.html', context)


# ===== CREATE USER =====
@login_required
@vendor_admin_required
@require_http_methods(["GET", "POST"])
def user_create(request):
    """
    Create a new user for the laboratory.
    """
    vendor = request.user.vendor
    
    if request.method == "POST":
        # Get form data
        email = request.POST.get('email', '').strip().lower()
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        contact_number = request.POST.get('contact_number', '').strip()
        role = request.POST.get('role', 'lab_staff')
        password = request.POST.get('password', '').strip()
        password_confirm = request.POST.get('password_confirm', '').strip()
        is_active = request.POST.get('is_active') == 'on'
        
        # Validation
        errors = []
        
        if not email:
            errors.append("Email is required.")
        elif User.objects.filter(email=email, vendor=vendor).exists():
            errors.append("A user with this email already exists in your laboratory.")
        
        if not first_name:
            errors.append("First name is required.")
        
        if not last_name:
            errors.append("Last name is required.")
        
        if not password:
            errors.append("Password is required.")
        elif len(password) < 8:
            errors.append("Password must be at least 8 characters long.")
        elif password != password_confirm:
            errors.append("Passwords do not match.")
        
        if role == 'platform_admin':
            errors.append("Cannot assign platform admin role.")
        
        if errors:
            for error in errors:
                messages.error(request, error)
        else:
            try:
                with transaction.atomic():
                    # Create user
                    user = User.objects.create_user(
                        email=email,
                        password=password,
                        first_name=first_name,
                        last_name=last_name,
                        contact_number=contact_number or None,
                        vendor=vendor,
                        role=role,
                        is_active=is_active,
                    )
                    
                    # Audit log
                    try:
                        from laboratory.models import AuditLog
                        AuditLog.objects.create(
                            vendor=vendor,
                            user=request.user,
                            action=f"Created new user: {user.get_full_name()} ({user.email}) with role {user.get_role_display_name()}",
                            ip_address=request.META.get('REMOTE_ADDR')
                        )
                    except ImportError:
                        pass
                    
                    messages.success(
                        request, 
                        f"User {user.get_full_name()} created successfully with role {user.get_role_display_name()}."
                    )
                    return redirect('users:user_detail', user_id=user.id)
                    
            except Exception as e:
                logger.exception(f"Error creating user: {e}")
                messages.error(request, f"Error creating user: {str(e)}")
    
    # Available roles (excluding platform_admin)
    available_roles = [
        choice for choice in User.ROLE_CHOICES 
        if choice[0] != 'platform_admin'
    ]
    
    context = {
        'available_roles': available_roles,
        'action': 'Create',
    }
    
    return render(request, 'users/user_form.html', context)


# ===== EDIT USER =====
@login_required
@vendor_admin_required
@require_http_methods(["GET", "POST"])
def user_edit(request, user_id):
    """
    Edit an existing user's information and role.
    """
    vendor = request.user.vendor
    user = get_object_or_404(
        User.objects.select_related('vendor'),
        id=user_id,
        vendor=vendor
    )
    
    # Prevent editing self
    if user.id == request.user.id:
        messages.error(request, "You cannot edit your own account here. Use profile settings.")
        return redirect('users:user_detail', user_id=user.id)
    
    if request.method == "POST":
        # Get form data
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        contact_number = request.POST.get('contact_number', '').strip()
        role = request.POST.get('role')
        is_active = request.POST.get('is_active') == 'on'
        
        # Validation
        errors = []
        
        if not first_name:
            errors.append("First name is required.")
        
        if not last_name:
            errors.append("Last name is required.")
        
        if role == 'platform_admin':
            errors.append("Cannot assign platform admin role.")
        
        if errors:
            for error in errors:
                messages.error(request, error)
        else:
            try:
                with transaction.atomic():
                    # Track changes for audit
                    changes = []
                    
                    if user.first_name != first_name:
                        changes.append(f"first name from '{user.first_name}' to '{first_name}'")
                        user.first_name = first_name
                    
                    if user.last_name != last_name:
                        changes.append(f"last name from '{user.last_name}' to '{last_name}'")
                        user.last_name = last_name
                    
                    if user.contact_number != contact_number:
                        changes.append(f"contact number")
                        user.contact_number = contact_number or None
                    
                    if user.role != role:
                        old_role = user.get_role_display_name()
                        changes.append(f"role from '{old_role}' to '{dict(User.ROLE_CHOICES)[role]}'")
                        user.role = role
                    
                    if user.is_active != is_active:
                        status = "activated" if is_active else "deactivated"
                        changes.append(f"account {status}")
                        user.is_active = is_active
                    
                    if changes:
                        user.save()
                        
                        # Audit log
                        try:
                            from laboratory.models import AuditLog
                            AuditLog.objects.create(
                                vendor=vendor,
                                user=request.user,
                                action=f"Updated user {user.get_full_name()}: {', '.join(changes)}",
                                ip_address=request.META.get('REMOTE_ADDR')
                            )
                        except ImportError:
                            pass
                        
                        messages.success(request, f"User {user.get_full_name()} updated successfully.")
                    else:
                        messages.info(request, "No changes were made.")
                    
                    return redirect('users:user_detail', user_id=user.id)
                    
            except Exception as e:
                logger.exception(f"Error updating user: {e}")
                messages.error(request, f"Error updating user: {str(e)}")
    
    # Available roles (excluding platform_admin)
    available_roles = [
        choice for choice in User.ROLE_CHOICES 
        if choice[0] != 'platform_admin'
    ]
    
    context = {
        'profile_user': user,
        'available_roles': available_roles,
        'action': 'Edit',
    }
    
    return render(request, 'users/user_form.html', context)


# ===== CHANGE USER ROLE (QUICK ACTION) =====
@login_required
@vendor_admin_required
@require_POST
def user_change_role(request, user_id):
    """
    Quick action to change a user's role from the list page.
    """
    vendor = request.user.vendor
    user = get_object_or_404(
        User.objects.select_related('vendor'),
        id=user_id,
        vendor=vendor
    )
    
    # Prevent changing own role
    if user.id == request.user.id:
        messages.error(request, "You cannot change your own role.")
        return redirect('users:user_list')
    
    new_role = request.POST.get('role')
    
    if not new_role or new_role not in dict(User.ROLE_CHOICES):
        messages.error(request, "Invalid role selected.")
        return redirect('users:user_list')
    
    if new_role == 'platform_admin':
        messages.error(request, "Cannot assign platform admin role.")
        return redirect('users:user_list')
    
    try:
        old_role_display = user.get_role_display_name()
        user.role = new_role
        user.save(update_fields=['role'])
        
        new_role_display = user.get_role_display_name()
        
        # Audit log
        try:
            from laboratory.models import AuditLog
            AuditLog.objects.create(
                vendor=vendor,
                user=request.user,
                action=f"Changed role of {user.get_full_name()} from '{old_role_display}' to '{new_role_display}'",
                ip_address=request.META.get('REMOTE_ADDR')
            )
        except ImportError:
            pass
        
        messages.success(
            request, 
            f"Role of {user.get_full_name()} changed from {old_role_display} to {new_role_display}."
        )
        
    except Exception as e:
        logger.exception(f"Error changing user role: {e}")
        messages.error(request, f"Error changing role: {str(e)}")
    
    return redirect('users:user_list')


# ===== TOGGLE USER STATUS =====
@login_required
@vendor_admin_required
@require_POST
def user_toggle_status(request, user_id):
    """
    Activate or deactivate a user account.
    """
    vendor = request.user.vendor
    user = get_object_or_404(
        User.objects.select_related('vendor'),
        id=user_id,
        vendor=vendor
    )
    
    # Prevent deactivating self
    if user.id == request.user.id:
        messages.error(request, "You cannot deactivate your own account.")
        return redirect('users:user_list')
    
    try:
        user.is_active = not user.is_active
        user.save(update_fields=['is_active'])
        
        status = "activated" if user.is_active else "deactivated"
        
        # Audit log
        try:
            from laboratory.models import AuditLog
            AuditLog.objects.create(
                vendor=vendor,
                user=request.user,
                action=f"{status.capitalize()} user account: {user.get_full_name()}",
                ip_address=request.META.get('REMOTE_ADDR')
            )
        except ImportError:
            pass
        
        messages.success(request, f"User {user.get_full_name()} {status} successfully.")
        
    except Exception as e:
        logger.exception(f"Error toggling user status: {e}")
        messages.error(request, f"Error: {str(e)}")
    
    return redirect('users:user_detail', user_id=user.id)


# ===== RESET PASSWORD =====
@login_required
@vendor_admin_required
@require_http_methods(["GET", "POST"])
def user_reset_password(request, user_id):
    """
    Reset a user's password (admin function).
    """
    vendor = request.user.vendor
    user = get_object_or_404(
        User.objects.select_related('vendor'),
        id=user_id,
        vendor=vendor
    )
    
    # Prevent resetting own password here
    if user.id == request.user.id:
        messages.error(request, "Use the profile settings to change your own password.")
        return redirect('users:user_detail', user_id=user.id)
    
    if request.method == "POST":
        new_password = request.POST.get('new_password', '').strip()
        confirm_password = request.POST.get('confirm_password', '').strip()
        
        if not new_password:
            messages.error(request, "Password is required.")
        elif len(new_password) < 8:
            messages.error(request, "Password must be at least 8 characters long.")
        elif new_password != confirm_password:
            messages.error(request, "Passwords do not match.")
        else:
            try:
                user.set_password(new_password)
                user.save(update_fields=['password'])
                
                # Audit log
                try:
                    from laboratory.models import AuditLog
                    AuditLog.objects.create(
                        vendor=vendor,
                        user=request.user,
                        action=f"Reset password for user: {user.get_full_name()}",
                        ip_address=request.META.get('REMOTE_ADDR')
                    )
                except ImportError:
                    pass
                
                messages.success(
                    request, 
                    f"Password reset successfully for {user.get_full_name()}. "
                    "The user can now log in with the new password."
                )
                return redirect('users:user_detail', user_id=user.id)
                
            except Exception as e:
                logger.exception(f"Error resetting password: {e}")
                messages.error(request, f"Error: {str(e)}")
    
    context = {
        'profile_user': user,
    }
    
    return render(request, 'users/user_reset_password.html', context)

