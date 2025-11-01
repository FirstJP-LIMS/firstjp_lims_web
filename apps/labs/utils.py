from django.db import transaction
from django.db.models import F
from apps.tenants.models import Vendor


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


# --- Sequence Generator Function for ids ---
def get_next_sequence(prefix: str, vendor: Vendor = None) -> str:
    """
    Thread-safe counter generator. 
    Each vendor (tenant) can have its own independent counters if needed.
    """
    from apps.labs.models import SequenceCounter 

    with transaction.atomic():
        counter, _ = SequenceCounter.objects.select_for_update().get_or_create(
            vendor=vendor,
            prefix=prefix,
            defaults={"last_number": 0}
        )
        counter.last_number = F("last_number") + 1
        counter.save()
        counter.refresh_from_db()
        return f"{prefix}{counter.last_number:06d}"

