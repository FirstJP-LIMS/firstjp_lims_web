# app/accounts/views.py
from django.shortcuts import render, redirect, get_object_or_404, Http404
from django.views.generic import TemplateView
from apps.tenants.models import Vendor
from ..forms import RegistrationForm, TenantAuthenticationForm, VendorProfile, VendorProfileForm, TenantPasswordResetForm
from django.urls import reverse, reverse_lazy
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import user_passes_test, login_required
from django.shortcuts import render, redirect
from django_ratelimit.decorators import ratelimit
from django.contrib.auth import get_user_model

User = get_user_model()

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

# ===== RESET PASSWORD =====
@login_required
# @vendor_admin_required
# @require_http_methods(["GET", "POST"])
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
                    from apps.labs.models import AuditLog
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

