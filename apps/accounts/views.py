# app/accounts/views.py
from django.shortcuts import render, redirect, get_object_or_404, Http404
from django.views.generic import TemplateView
from apps.tenants.models import Vendor
from .forms import RegistrationForm, TenantAuthenticationForm
from django.urls import reverse, reverse_lazy
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from .forms import TenantAuthenticationForm
from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import render, redirect

# ----------------------------------
# Tenant-aware auth. 
# ----------------------------------
# laboris@gmail.com
# password#12345

# lastborn.ai@gmail.com
# password#1234


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


# def tenant_login(request):
#     vendorInfo = Vendor.objects.prefetch_related('name')
#     tenant = getattr(request, 'tenant', None)
#     if request.method == 'POST':
#         form = TenantAuthenticationForm(request, data=request.POST)
#         if form.is_valid():
#             user = form.get_user()
#             # Platform Admin: global access
#             if getattr(user, 'is_platform_admin', False):
#                 login(request, user)
#                 messages.success(request, f"Welcome back, {user.email}")
#                 return redirect(reverse('dashboard'))
#             # Vendor/Lab Staff: tenant-restricted
#             if not tenant:
#                 messages.error(request, "No tenant could be resolved. Access denied.")
#                 return redirect(reverse('no_tenant'))

#             if user.vendor_id and user.vendor_id == tenant.internal_id:
#                 login(request, user)
#                 messages.success(request, f"Welcome, {user.email}")
#                 return redirect(reverse('labs:vendor_dashboard'))
#             messages.error(request, "Invalid tenant or user mismatch.")
#             return redirect(reverse('login'))
#     else:
#         form = TenantAuthenticationForm(request)
#     # pass tenant object  
#     context = {
#         'form': form,
#         'tenant': tenant,
#         'vendorInfo': vendorInfo,
#     }
#     return render(request, 'registration/login.html', context)


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
    return render(request, 'registration/login.html', context)



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

