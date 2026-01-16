# # apps/core/middleware.py 
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
    - Recognizes the special learning portal subdomain (learn.<PLATFORM_BASE_DOMAIN>)
    """

    def process_request(self, request):
        host = request.get_host().split(':')[0].lower()
        tenant_header = request.headers.get('X-Tenant-ID') or request.META.get('HTTP_X_TENANT_ID')
        tenant = None

        # 0. Special-case: learning portal - treat as a non-tenant platform zone
        platform_base = getattr(settings, "PLATFORM_BASE_DOMAIN", "localhost.test")
        learn_host = f"learn.{platform_base}".lower()
        request.is_learning_portal = (host == learn_host)

        # 1. Header-based tenant lookup (API clients) - only if not learning portal
        if tenant_header and not request.is_learning_portal:
            tenant = self._get_tenant_by_header(tenant_header)

        # 2. Domain-based tenant lookup (browser access) - only if not learning portal
        if not tenant and not request.is_learning_portal:
            tenant = self._get_tenant_by_domain(host)

        # 3. Attach tenant or set platform mode
        request.tenant = tenant
        request.is_platform = (tenant is None and not request.is_learning_portal)

        # 4. Reject unknown vendor subdomains (only when not platform and not learning portal)
        if not tenant and not request.is_platform and not request.is_learning_portal:
            # host is not recognized as vendor domain, not in global hosts
            if host not in getattr(settings, "GLOBAL_HOSTS", []):
                return HttpResponseNotFound(
                    "<h1>Vendor Not Found</h1>"
                    "<p>This laboratory subdomain is not registered or has been deactivated.</p>"
                    f"<p><a href='https://{settings.PLATFORM_BASE_DOMAIN}'>Return to main platform</a></p>"
                )

        # 5. Redirect vendor root to vendor login
        if tenant and request.path == "/":
            return HttpResponseRedirect(reverse('account:login'))

        # 5b. Redirect learning portal root "/" to learning landing page
        if request.is_learning_portal and request.path == "/":
            # return HttpResponseRedirect(reverse('lms:index'))
            return HttpResponseRedirect(reverse('learn:index'))

        return None

    # ------------------------------------
    # INTERNAL METHODS (NO CACHE)
    # ------------------------------------

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


