from .models import VendorProfile

def vendor_context(request):
    vendor = getattr(request, "tenant", None)
    vendor_profile = None

    if vendor:
        try:
            vendor_profile = VendorProfile.objects.get(vendor=vendor)
        except VendorProfile.DoesNotExist:
            vendor_profile = None

    return {
        "vendor": vendor,
        "vendor_profile": vendor_profile,
    }
