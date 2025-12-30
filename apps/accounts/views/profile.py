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

