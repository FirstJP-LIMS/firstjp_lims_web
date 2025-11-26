from django.utils.deprecation import MiddlewareMixin
from django.http import HttpResponseRedirect, HttpResponseNotFound
from django.conf import settings
from django.urls import reverse
from django.core.cache import cache
from apps.tenants.models import VendorDomain, Vendor
import logging

logger = logging.getLogger(__name__)


class TenantMiddleware(MiddlewareMixin):
    """
    Optimized tenant resolution with caching for production.
    Supports both API (header-based) and browser (subdomain-based) access.
    """
    
    CACHE_TTL = 60 * 15  # Cache for 15 minutes
    CACHE_NEGATIVE_TTL = 60 * 5  # Cache "not found" for 5 minutes
    
    def process_request(self, request):
        host = request.get_host().split(':')[0].lower()
        tenant_header = request.headers.get('X-Tenant-ID') or request.META.get('HTTP_X_TENANT_ID')
        tenant = None
        
        # 1️⃣ Header-based tenant resolution (for API clients)
        if tenant_header:
            tenant = self._get_tenant_by_header(tenant_header)
        
        # 2️⃣ Domain-based tenant resolution (for browser subdomains)
        if not tenant:
            tenant = self._get_tenant_by_domain(host)
        
        # 3️⃣ Attach tenant to request
        request.tenant = tenant
        request.is_platform = tenant is None
        
        # 4️⃣ Handle missing or inactive tenants
        if not tenant and host not in getattr(settings, "GLOBAL_HOSTS", []):
            return HttpResponseNotFound(
                "<h1>Vendor not found</h1>"
                "<p>This laboratory subdomain is not registered or has been deactivated.</p>"
                f"<p><a href='https://{settings.PLATFORM_BASE_DOMAIN}'>Return to main platform</a></p>"
            )
        
        # 5️⃣ Redirect vendor subdomain root to vendor login
        if tenant and request.path == "/":
            return HttpResponseRedirect(reverse('account:login'))
        
        return None
    
    def _get_tenant_by_header(self, tenant_id):
        """Get tenant by X-Tenant-ID header (cached)"""
        cache_key = f"tenant_header_{tenant_id}"
        
        try:
            tenant = cache.get(cache_key)
        except Exception as e:
            logger.error(f"Cache error in _get_tenant_by_header: {e}")
            tenant = None
        
        if tenant is None:
            try:
                tenant = Vendor.objects.select_related('vendorprofile').get(
                    tenant_id=tenant_id,
                    is_active=True
                )
                try:
                    cache.set(cache_key, tenant, self.CACHE_TTL)
                except Exception as e:
                    logger.error(f"Cache set error: {e}")
                    
            except Vendor.DoesNotExist:
                try:
                    # Cache negative result with shorter TTL
                    cache.set(cache_key, False, self.CACHE_NEGATIVE_TTL)
                except Exception as e:
                    logger.error(f"Cache set error: {e}")
                return None
        
        return tenant if tenant else None
    
    def _get_tenant_by_domain(self, host):
        """Get tenant by domain name (cached)"""
        cache_key = f"tenant_domain_{host}"
        
        try:
            tenant = cache.get(cache_key)
        except Exception as e:
            logger.error(f"Cache error in _get_tenant_by_domain: {e}")
            tenant = None
        
        if tenant is None:
            try:
                domain = VendorDomain.objects.select_related(
                    'vendor',
                    'vendor__vendorprofile'
                ).get(domain_name=host)
                
                if domain.vendor.is_active:
                    tenant = domain.vendor
                    try:
                        cache.set(cache_key, tenant, self.CACHE_TTL)
                    except Exception as e:
                        logger.error(f"Cache set error: {e}")
                else:
                    try:
                        cache.set(cache_key, False, self.CACHE_NEGATIVE_TTL)
                    except Exception as e:
                        logger.error(f"Cache set error: {e}")
                    return None
                    
            except VendorDomain.DoesNotExist:
                try:
                    cache.set(cache_key, False, self.CACHE_NEGATIVE_TTL)
                except Exception as e:
                    logger.error(f"Cache set error: {e}")
                return None
        
        return tenant if tenant else None


# Optional: Clear cache when vendor is updated
def clear_tenant_cache(vendor):
    """Clear all cache entries for a specific vendor"""
    try:
        cache.delete(f"tenant_header_{vendor.tenant_id}")
        for domain in vendor.domains.all():
            cache.delete(f"tenant_domain_{domain.domain_name}")
        logger.info(f"Cleared cache for vendor: {vendor.tenant_id}")
    except Exception as e:
        logger.error(f"Error clearing cache: {e}")



# from django.utils.deprecation import MiddlewareMixin
# from django.http import HttpResponseRedirect, HttpResponseNotFound
# from django.conf import settings
# from django.urls import reverse
# from apps.tenants.models import VendorDomain, Vendor


# class TenantMiddleware(MiddlewareMixin):
#     def process_request(self, request):
#         host = request.get_host().split(':')[0].lower()
#         tenant_header = request.headers.get('X-Tenant-ID') or request.META.get('HTTP_X_TENANT_ID')
#         tenant = None

#         # 1️⃣ Header-based tenant resolution (for API clients)
#         if tenant_header:
#             try:
#                 tenant = Vendor.objects.get(tenant_id=tenant_header, is_active=True)
#             except Vendor.DoesNotExist:
#                 pass

#         # 2️⃣ Domain-based tenant resolution (for browser subdomains)
#         if not tenant:
#             try:
#                 domain = VendorDomain.objects.select_related('vendor').get(domain_name=host)
#                 if domain.vendor.is_active:
#                     tenant = domain.vendor
#             except VendorDomain.DoesNotExist:
#                 pass

#         # 3️⃣ Attach tenant or reject
#         request.tenant = tenant

#         # 4️⃣ Handle missing or inactive tenants
#         if not tenant and host not in getattr(settings, "GLOBAL_HOSTS", []):
#             return HttpResponseNotFound("Vendor not found or inactive.")

#         # 5️⃣ Optionally redirect vendor subdomain root to vendor login
#         if tenant and request.path == "/":
#             # Redirect vendor root (like coarbon12.localhost.test:5050) → /vendor/login/
#             return HttpResponseRedirect(reverse('account:login'))
#         return None

