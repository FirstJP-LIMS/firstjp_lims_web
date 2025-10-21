from django.utils.deprecation import MiddlewareMixin
from django.http import HttpResponseNotFound
from django.conf import settings
from apps.tenants.models import VendorDomain, Vendor


class TenantMiddleware(MiddlewareMixin):
    def process_request(self, request):
        host = request.get_host().split(':')[0].lower()
        tenant_header = request.headers.get('X-Tenant-ID') or request.META.get('HTTP_X_TENANT_ID')
        tenant = None

        # 1️⃣ Header-based resolution
        if tenant_header:
            try:
                tenant = Vendor.objects.get(tenant_id=tenant_header, is_active=True)
            except Vendor.DoesNotExist:
                pass

        # 2️⃣ Domain-based resolution
        if not tenant:
            try:
                domain = VendorDomain.objects.select_related('vendor').get(domain_name=host)
                if domain.vendor.is_active:
                    tenant = domain.vendor
            except VendorDomain.DoesNotExist:
                pass

        # 3️⃣ Attach to request or deny
        request.tenant = tenant
        if not tenant and host not in getattr(settings, "GLOBAL_HOSTS", []):
            return HttpResponseNotFound("Tenant not found or inactive.")
