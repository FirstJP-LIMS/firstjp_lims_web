from django.utils.deprecation import MiddlewareMixin
from django.http import HttpResponseRedirect, HttpResponseNotFound
from django.conf import settings
from django.urls import reverse
from apps.tenants.models import VendorDomain, Vendor


class TenantMiddleware(MiddlewareMixin):
    def process_request(self, request):
        host = request.get_host().split(':')[0].lower()
        tenant_header = request.headers.get('X-Tenant-ID') or request.META.get('HTTP_X_TENANT_ID')
        tenant = None

        # 1️⃣ Header-based tenant resolution (for API clients)
        if tenant_header:
            try:
                tenant = Vendor.objects.get(tenant_id=tenant_header, is_active=True)
            except Vendor.DoesNotExist:
                pass

        # 2️⃣ Domain-based tenant resolution (for browser subdomains)
        if not tenant:
            try:
                domain = VendorDomain.objects.select_related('vendor').get(domain_name=host)
                if domain.vendor.is_active:
                    tenant = domain.vendor
            except VendorDomain.DoesNotExist:
                pass

        # 3️⃣ Attach tenant or reject
        request.tenant = tenant

        # 4️⃣ Handle missing or inactive tenants
        if not tenant and host not in getattr(settings, "GLOBAL_HOSTS", []):
            return HttpResponseNotFound("Vendor not found or inactive.")

        # 5️⃣ Optionally redirect vendor subdomain root to vendor login
        if tenant and request.path == "/":
            # Redirect vendor root (like coarbon12.localhost.test:5050) → /vendor/login/
            return HttpResponseRedirect(reverse('account:login'))
        return None



# # middleware.py
# from django.utils.deprecation import MiddlewareMixin
# from django.http import HttpResponseNotFound
# from django.conf import settings
# from apps.tenants.models import VendorDomain, Vendor


# class TenantMiddleware(MiddlewareMixin):
#     def process_request(self, request):
#         host = request.get_host().split(':')[0].lower()
#         tenant_header = request.headers.get('X-Tenant-ID') or request.META.get('HTTP_X_TENANT_ID')
#         tenant = None

#         # 1️⃣ Header-based resolution (Existing Logic)
#         if tenant_header:
#             try:
#                 tenant = Vendor.objects.get(tenant_id=tenant_header, is_active=True)
#             except Vendor.DoesNotExist:
#                 pass

#         # 2️⃣ Domain-based resolution (Existing Logic)
#         if not tenant:
#             try:
#                 domain = VendorDomain.objects.select_related('vendor').get(domain_name=host)
#                 if domain.vendor.is_active:
#                     tenant = domain.vendor
#             except VendorDomain.DoesNotExist:
#                 pass

#         # 3️⃣ Attach tenant to request
#         request.tenant = tenant
        
#         # 4️⃣ Dynamic Routing Fix: Set the URL configuration
#         # If a tenant is successfully resolved (e.g., coarbon12.localhost.test:5050)
#         if tenant:
#             # The Vendor's URL configuration, e.g., mapping to their dashboard,
#             # login, and all LIMS views.
#             # request.urlconf = settings.VENDOR_URLCONF 
#             path = VendorDomain.objects.get(vendor=tenant, is_primary=True).domain_name 
#             request.urlconf = path  # e.g., carbonilab.localhost.test 
        
#         # If no tenant is resolved, check if the host is a global one (e.g., localhost.test)
#         # If it's a global host, it will use the main ROOT_URLCONF defined in settings.
#         # If it's NOT a global host AND no tenant was found, show 404.
#         elif host not in getattr(settings, "GLOBAL_HOSTS", []):
#             return HttpResponseNotFound("Tenant not found or inactive.")
            
#         # Note: If tenant is None and host IS a GLOBAL_HOST, request.urlconf remains 
#         # the default settings.ROOT_URLCONF, allowing access to the main public site (e.g., pricing, global login).



# # from django.utils.deprecation import MiddlewareMixin
# # from django.http import HttpResponseNotFound
# # from django.conf import settings
# # from apps.tenants.models import VendorDomain, Vendor


# # class TenantMiddleware(MiddlewareMixin):
# #     def process_request(self, request):
# #         host = request.get_host().split(':')[0].lower()
# #         tenant_header = request.headers.get('X-Tenant-ID') or request.META.get('HTTP_X_TENANT_ID')
# #         tenant = None

# #         # 1️⃣ Header-based resolution
# #         if tenant_header:
# #             try:
# #                 tenant = Vendor.objects.get(tenant_id=tenant_header, is_active=True)
# #             except Vendor.DoesNotExist:
# #                 pass

# #         # 2️⃣ Domain-based resolution
# #         if not tenant:
# #             try:
# #                 domain = VendorDomain.objects.select_related('vendor').get(domain_name=host)
# #                 if domain.vendor.is_active:
# #                     tenant = domain.vendor
# #             except VendorDomain.DoesNotExist:
# #                 pass

# #         # 3️⃣ Attach to request or deny
# #         request.tenant = tenant
# #         if not tenant and host not in getattr(settings, "GLOBAL_HOSTS", []):
# #             return HttpResponseNotFound("Tenant not found or inactive.")
