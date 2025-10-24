"""
PATIENT  →  SAMPLE(S)  →  TEST REQUEST(S)  →  RESULT(S)
   |             |              |                  |
   |          Sample ID      Test ID           Verified / Released
   |             |              |
Doctor → Clinical Info    Department → Test Type

"""
# apps/labs/views.py
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from functools import wraps
from .utils import check_tenant_access


# --- Decorator Definition ---
def tenant_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        tenant, is_platform_admin = check_tenant_access(request)
        if not tenant and not is_platform_admin:
            return HttpResponseForbidden("Access Denied: Tenant or User Mismatch.")
        # Attach resolved values to request for easy use in the view
        request.tenant = tenant
        request.is_platform_admin = is_platform_admin
        return view_func(request, *args, **kwargs)
    return _wrapped_view


# --- CRM Views ---
@login_required
@tenant_required
def dashboard(request):
    tenant = request.tenant
    is_platform_admin = request.is_platform_admin

    if is_platform_admin and not tenant:
        return render(request, "crm/tenant_index.html") # for registering of lab assistant

    lab_name = getattr(tenant, 'business_name', tenant.name)
    context = {
        "vendor": tenant,
        "lab_name": lab_name,
        "vendor_domain": tenant.domains.first().domain_name if tenant.domains.exists() else None,
    }
    return render(request, "crm/dashboard.html", context)


@login_required
@tenant_required
def lab_assistants(request):
    tenant = request.tenant
    assistants = request.user._meta.model.objects.filter(vendor=tenant, role='lab_staff')
    return render(request, "crm/assistants.html", {"assistants": assistants})


@login_required
@tenant_required
def profile(request):
    return render(request,"crm/profile.html",
        {"vendor": request.tenant, "user": request.user}
    )


