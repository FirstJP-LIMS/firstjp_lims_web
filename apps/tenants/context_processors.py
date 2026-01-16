from django.shortcuts import get_object_or_404
from . models import Vendor

# def vendor_context(request):
#     """
#     Add the current vendor to the template context based on subdomain.
#     """
#     subdomain_prefix = getattr(request, 'subdomain_prefix', None)
    
#     if subdomain_prefix:
#         try:
#             vendor = Vendor.objects.get(subdomain_prefix=subdomain_prefix, is_active=True)
#             return {'vendor': vendor}
#         except Vendor.DoesNotExist:
#             pass
    
#     return {'vendor': None}


def vendor_context(request):
    return {
        'vendor': getattr(request, 'tenant', None)
    }
