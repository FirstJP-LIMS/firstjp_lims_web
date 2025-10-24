# --- Core Security Check Function ---
def check_tenant_access(request):
    """
    Ensures the user is logged in AND belongs to the resolved tenant.
    Returns (tenant, is_platform_admin) or None if access is denied.
    """
    tenant = getattr(request, "tenant", None)
    user = request.user

    # Platform Admin always has access
    is_platform_admin = getattr(user, 'is_platform_admin', False)
    if is_platform_admin:
        return tenant, is_platform_admin

    # Tenant match check
    if tenant and user.is_authenticated and user.vendor_id == tenant.internal_id:
        return tenant, is_platform_admin

    # Deny if mismatch
    return None, is_platform_admin