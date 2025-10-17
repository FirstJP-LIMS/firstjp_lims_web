# core/middleware.py
from django.utils.deprecation import MiddlewareMixin
from tenants.models import VendorDomain
from django.http import HttpResponseNotFound


class TenantMiddleware(MiddlewareMixin):
    """
    Resolves tenant based on domain or tenant_id (header).
    Attaches `request.tenant` for use throughout the request lifecycle.
    """

    def process_request(self, request):
        host = request.get_host().split(':')[0].lower()

        # Optional: Allow API clients (like Windows Service) to send X-Tenant-ID
        tenant_id = request.headers.get('X-Tenant-ID')

        try:
            if tenant_id:
                domain_obj = VendorDomain.objects.select_related('vendor').filter(
                    vendor__tenant_id=tenant_id, vendor__is_active=True
                ).first()
            else:
                domain_obj = VendorDomain.objects.select_related('vendor').get(
                    domain_name=host
                )

            request.tenant = domain_obj.vendor if domain_obj else None

        except VendorDomain.DoesNotExist:
            request.tenant = None

        # Optional: Handle no tenant found
        if not request.tenant:
            # Could redirect to a marketing page or raise 404
            return HttpResponseNotFound("Tenant not found or inactive.")
