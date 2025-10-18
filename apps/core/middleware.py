# # core/middleware.py
from django.utils.deprecation import MiddlewareMixin
from apps.tenants.models import VendorDomain, Vendor # Import Vendor for clarity
from django.http import HttpResponseNotFound
from django.conf import settings

class TenantMiddleware(MiddlewareMixin):
    """
    Resolves tenant based on domain or X-Tenant-ID header.
    Attaches `request.tenant` for use throughout the request lifecycle.
    """
    def process_request(self, request):
        host = request.get_host().split(':')[0].lower()
        tenant_header = request.headers.get('X-Tenant-ID') or request.META.get('HTTP_X_TENANT_ID')

        tenant = None
        
        # 1. Resolve Tenant via Header (for APIs, tests, Windows service)
        if tenant_header:
            # Assumes tenant_header is the human-readable tenant_id slug
            try:
                # Use Vendor model directly for efficiency if we are looking up by tenant_id slug
                tenant = Vendor.objects.get(tenant_id=tenant_header, is_active=True)
            except Vendor.DoesNotExist:
                tenant = None

        # 2. Resolve Tenant via Domain (for web browsers)
        if not tenant:
            try:
                domain = VendorDomain.objects.select_related('vendor').get(domain_name=host)
                # Check if the resolved vendor is active
                if domain.vendor.is_active:
                    tenant = domain.vendor
            except VendorDomain.DoesNotExist:
                tenant = None

        request.tenant = tenant

        # Guard: Block requests if tenant cannot be resolved AND it's not a global page.
        # This is the security firewall.
        if not request.tenant and host not in settings.GLOBAL_HOSTS: 
            # settings.GLOBAL_HOSTS would list marketing.com, api.com, etc.
            return HttpResponseNotFound("Tenant not found or inactive.")
        
        # NOTE: For Platform Admins accessing the login/admin site, 
        # request.tenant will be None, which is fine, as long as your
        # login view handles it.


# from django.utils.deprecation import MiddlewareMixin
# from tenants.models import VendorDomain
# from django.http import HttpResponseNotFound


# class TenantMiddleware(MiddlewareMixin):
#     """
#     Resolves tenant based on domain or tenant_id (header).
#     Attaches `request.tenant` for use throughout the request lifecycle.
#     """

#     def process_request(self, request):
#         host = request.get_host().split(':')[0].lower()

#         # Allow explicit header override (useful for API clients / tests)
#         tenant_header = request.headers.get('X-Tenant-ID') or request.META.get('HTTP_X_TENANT_ID')

#         tenant = None
#         if tenant_header:
#             # tenant_header expected to be tenant_id (human readable) or UUID
#             domain_qs = VendorDomain.objects.select_related('vendor').filter(vendor__tenant_id=tenant_header)
#             domain = domain_qs.first()
#             if domain:
#                 tenant = domain.vendor
#         else:
#             try:
#                 domain = VendorDomain.objects.select_related('vendor').get(domain_name=host)
#                 tenant = domain.vendor
#             except VendorDomain.DoesNotExist:
#                 tenant = None

#         request.tenant = tenant

#         # Optional: Handle no tenant found
#         if not request.tenant:
#             # Could redirect to a marketing page or raise 404
#             return HttpResponseNotFound("Tenant not found or inactive.")
