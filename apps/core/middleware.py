from django.utils.deprecation import MiddlewareMixin
from django.http import HttpResponseRedirect, HttpResponseNotFound
from django.conf import settings
from django.urls import reverse
from apps.tenants.models import VendorDomain, Vendor
import logging

logger = logging.getLogger(__name__)


class TenantMiddleware(MiddlewareMixin):
    """
    Tenant Middleware (NO CACHING)
    - Supports API header "X-Tenant-ID"
    - Supports browser subdomains (VendorDomain)
    - Performs direct DB lookup only
    """

    def process_request(self, request):
        host = request.get_host().split(':')[0].lower()
        tenant_header = request.headers.get('X-Tenant-ID') or request.META.get('HTTP_X_TENANT_ID')
        tenant = None

        # 1️⃣ Header-based tenant lookup (API clients)
        if tenant_header:
            tenant = self._get_tenant_by_header(tenant_header)

        # 2️⃣ Domain-based tenant lookup (browser access)
        if not tenant:
            tenant = self._get_tenant_by_domain(host)

        # 3️⃣ Attach tenant or set platform mode
        request.tenant = tenant
        request.is_platform = tenant is None

        # 4️⃣ Reject unknown vendor subdomains
        if not tenant and host not in getattr(settings, "GLOBAL_HOSTS", []):
            return HttpResponseNotFound(
                "<h1>Vendor Not Found</h1>"
                "<p>This laboratory subdomain is not registered or has been deactivated.</p>"
                f"<p><a href='https://{settings.PLATFORM_BASE_DOMAIN}'>Return to main platform</a></p>"
            )

        # 5️⃣ Redirect vendor root to vendor login
        if tenant and request.path == "/":
            return HttpResponseRedirect(reverse('account:login'))

        return None

    # ----------------------------------------------------------------------
    # INTERNAL METHODS (NO CACHE)
    # ----------------------------------------------------------------------

    def _get_tenant_by_header(self, tenant_id):
        """Resolve tenants via X-Tenant-ID header (direct DB lookup)."""
        try:
            return Vendor.objects.get(
                tenant_id=tenant_id,
                is_active=True
            )
        except Vendor.DoesNotExist:
            return None

    def _get_tenant_by_domain(self, host):
        """Resolve tenants via VendorDomain (direct DB lookup)."""
        try:
            domain = VendorDomain.objects.select_related('vendor').get(
                domain_name=host
            )
            return domain.vendor if domain.vendor.is_active else None
        except VendorDomain.DoesNotExist:
            return None


# # ----------------------------------------------------------------------
# # OPTIONAL: EMPTY CACHE CLEAR (kept for compatibility)
# # ----------------------------------------------------------------------
# def clear_tenant_cache(vendor):
#     """No-op because caching is disabled."""
#     logger.info(f"No cache to clear for vendor: {vendor.tenant_id}")



# # from django.utils.deprecation import MiddlewareMixin
# # from django.http import HttpResponseRedirect, HttpResponseNotFound
# # from django.conf import settings
# # from django.urls import reverse
# # from django.core.cache import cache
# # from apps.tenants.models import VendorDomain, Vendor
# # import logging

# # logger = logging.getLogger(__name__)


# class TenantMiddleware(MiddlewareMixin):
#     """
#     Production-optimized Tenant Middleware
#     - Supports API header "X-Tenant-ID"
#     - Supports browser subdomains (VendorDomain)
#     - Caches lookups for speed
#     """

#     CACHE_TTL = 60 * 15          # Cache valid vendors for 15 minutes
#     CACHE_NEGATIVE_TTL = 60 * 5  # Cache "not found" cases for 5 minutes

#     def process_request(self, request):
#         host = request.get_host().split(':')[0].lower()
#         tenant_header = request.headers.get('X-Tenant-ID') or request.META.get('HTTP_X_TENANT_ID')
#         tenant = None

#         # 1️⃣ Header-based tenant lookup (API clients)
#         if tenant_header:
#             tenant = self._get_tenant_by_header(tenant_header)

#         # 2️⃣ Domain-based tenant lookup (browser access)
#         if not tenant:
#             tenant = self._get_tenant_by_domain(host)

#         # 3️⃣ Attach tenant or set platform mode
#         request.tenant = tenant
#         request.is_platform = tenant is None

#         # 4️⃣ Reject unknown vendor subdomains
#         if not tenant and host not in getattr(settings, "GLOBAL_HOSTS", []):
#             return HttpResponseNotFound(
#                 "<h1>Vendor Not Found</h1>"
#                 "<p>This laboratory subdomain is not registered or has been deactivated.</p>"
#                 f"<p><a href='https://{settings.PLATFORM_BASE_DOMAIN}'>Return to main platform</a></p>"
#             )

#         # 5️⃣ Redirect vendor root to vendor login
#         if tenant and request.path == "/":
#             return HttpResponseRedirect(reverse('account:login'))

#         return None

#     # ----------------------------------------------------------------------
#     # INTERNAL METHODS
#     # ----------------------------------------------------------------------

#     def _get_tenant_by_header(self, tenant_id):
#         """Resolve tenants via X-Tenant-ID header (cached)."""
#         cache_key = f"tenant_header_{tenant_id}"

#         try:
#             tenant = cache.get(cache_key)
#         except Exception as e:
#             logger.error(f"Cache error (header): {e}")
#             tenant = None

#         if tenant is None:
#             try:
#                 tenant = Vendor.objects.get(
#                     tenant_id=tenant_id,
#                     is_active=True
#                 )
#                 cache.set(cache_key, tenant, self.CACHE_TTL)

#             except Vendor.DoesNotExist:
#                 cache.set(cache_key, False, self.CACHE_NEGATIVE_TTL)
#                 return None

#         return tenant if tenant else None

#     def _get_tenant_by_domain(self, host):
#         """Resolve tenants via VendorDomain (cached)."""
#         cache_key = f"tenant_domain_{host}"

#         try:
#             tenant = cache.get(cache_key)
#         except Exception as e:
#             logger.error(f"Cache error (domain): {e}")
#             tenant = None

#         if tenant is None:
#             try:
#                 domain = VendorDomain.objects.select_related('vendor').get(
#                     domain_name=host
#                 )

#                 if domain.vendor.is_active:
#                     tenant = domain.vendor
#                     cache.set(cache_key, tenant, self.CACHE_TTL)
#                 else:
#                     cache.set(cache_key, False, self.CACHE_NEGATIVE_TTL)
#                     return None

#             except VendorDomain.DoesNotExist:
#                 cache.set(cache_key, False, self.CACHE_NEGATIVE_TTL)
#                 return None

#         return tenant if tenant else None


# # ----------------------------------------------------------------------
# # OPTIONAL: AUTOMATIC CACHE CLEARING WHEN VENDOR UPDATES
# # ----------------------------------------------------------------------
# def clear_tenant_cache(vendor):
#     """Manually clear all cached entries for a specific vendor."""
#     try:
#         cache.delete(f"tenant_header_{vendor.tenant_id}")

#         for domain in vendor.domains.all():
#             cache.delete(f"tenant_domain_{domain.domain_name}")

#         logger.info(f"Cache cleared for vendor: {vendor.tenant_id}")

#     except Exception as e:
#         logger.error(f"Error clearing tenant cache: {e}")


# # from django.utils.deprecation import MiddlewareMixin
# # from django.http import HttpResponseRedirect, HttpResponseNotFound
# # from django.conf import settings
# # from django.urls import reverse
# # from apps.tenants.models import VendorDomain, Vendor


# # class TenantMiddleware(MiddlewareMixin):
# #     def process_request(self, request):
# #         host = request.get_host().split(':')[0].lower()
# #         tenant_header = request.headers.get('X-Tenant-ID') or request.META.get('HTTP_X_TENANT_ID')
# #         tenant = None

# #         # 1️⃣ Header-based tenant resolution (for API clients)
# #         if tenant_header:
# #             try:
# #                 tenant = Vendor.objects.get(tenant_id=tenant_header, is_active=True)
# #             except Vendor.DoesNotExist:
# #                 pass

# #         # 2️⃣ Domain-based tenant resolution (for browser subdomains)
# #         if not tenant:
# #             try:
# #                 domain = VendorDomain.objects.select_related('vendor').get(domain_name=host)
# #                 if domain.vendor.is_active:
# #                     tenant = domain.vendor
# #             except VendorDomain.DoesNotExist:
# #                 pass

# #         # 3️⃣ Attach tenant or reject
# #         request.tenant = tenant

# #         # 4️⃣ Handle missing or inactive tenants
# #         if not tenant and host not in getattr(settings, "GLOBAL_HOSTS", []):
# #             return HttpResponseNotFound("Vendor not found or inactive.")

# #         # 5️⃣ Optionally redirect vendor subdomain root to vendor login
# #         if tenant and request.path == "/":
# #             # Redirect vendor root (like coarbon12.localhost.test:5050) → /vendor/login/
# #             return HttpResponseRedirect(reverse('account:login'))
# #         return None

