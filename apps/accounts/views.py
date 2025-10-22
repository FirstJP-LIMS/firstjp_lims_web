# app/accounts/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import TemplateView
from apps.tenants.models import Vendor
from .forms import RegistrationForm, TenantAuthenticationForm
from django.urls import reverse, reverse_lazy
from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from .forms import TenantAuthenticationForm
from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import render, redirect


def tenant_register(request):
    tenant = getattr(request, 'tenant', None)

    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if not tenant:
            messages.error(request, "Tenant could not be resolved. Contact support.")
            return render(request, 'registration/register.html', {'form': form})

        if form.is_valid():
            form.save(vendor=tenant, role='lab_staff')
            messages.success(request, "Registration successful. You can now log in.")
            return redirect(reverse('login'))
    else:
        form = RegistrationForm()

    return render(request, 'registration/register.html', {'form': form})


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
    tenant = getattr(request, 'tenant', None)
    if request.method == 'POST':
        form = TenantAuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()

            # Platform Admin: global access
            if getattr(user, 'is_platform_admin', False):
                auth_login(request, user)
                messages.success(request, f"Welcome back, {user.email}")
                return redirect(reverse('dashboard'))  # Adjust destination as needed

            # Vendor/Lab Staff: tenant-restricted
            if not tenant:
                messages.error(request, "No tenant could be resolved. Access denied.")
                return redirect(reverse('no_tenant'))

            if user.vendor_id and user.vendor_id == tenant.internal_id:
                auth_login(request, user)
                messages.success(request, f"Welcome, {user.email}")
                return redirect(reverse('vendor_dashboard'))

            messages.error(request, "Invalid tenant or user mismatch.")
            return redirect(reverse('login'))
    else:
        form = TenantAuthenticationForm(request)

    return render(request, 'registration/login.html', {'form': form})


# def tenant_login(request):
#     tenant = getattr(request, 'tenant', None)

#     if request.method == 'POST':
#         form = TenantAuthenticationForm(request, data=request.POST)
#         if form.is_valid():
#             user = form.get_user()

#             # Platform Admin: global access
#             if getattr(user, 'is_platform_admin', False):
#                 auth_login(request, user)
#                 messages.success(request, f"Welcome back, {user.email}")
#                 return redirect('dashboard')

#             # Tenant (Vendor/Lab Staff) Access
#             if tenant and user.vendor_id == tenant.internal_id:
#                 auth_login(request, user)
#                 messages.success(request, f"Welcome, {user.email}")
#                 return redirect('vendor_dashboard')

#             messages.error(request, "Invalid tenant or user mismatch.")
#         else:
#             messages.error(request, "Invalid login credentials.")
#     else:
#         form = TenantAuthenticationForm(request)

#     return render(request, 'registration/login.html', {'form': form})


# ------------------------------
# Tenant-Aware Logout View (FBV)
# ------------------------------
def tenant_logout(request):
    auth_logout(request)
    messages.info(request, "You have been logged out successfully.")
    return redirect(reverse_lazy('login'))


class DashboardView(TemplateView):
    template_name = 'admin_ui/dashboard.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['tenant'] = getattr(self.request, 'tenant', None)
        return ctx

