from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
from .models import Vendor, VendorDomain


@receiver(post_save, sender=Vendor)
def handle_vendor_domain(sender, instance, created, **kwargs):
    """
    Constructs the full domain name and ensures a primary VendorDomain object exists
    and is active when Vendor.is_active is set to True.
    """
    if not instance.is_active:
        return

    subdomain = (
        instance.subdomain_prefix.lower()
        if instance.subdomain_prefix
        else instance.tenant_id.lower()
    )
    base_domain = getattr(settings, 'PLATFORM_BASE_DOMAIN', 'localhost.test')
    full_domain = f"{subdomain}.{base_domain}"

    domain_obj, created_domain = VendorDomain.objects.get_or_create(
        vendor=instance,
        defaults={'domain_name': full_domain, 'is_primary': True}
    )

    if not created_domain and domain_obj.domain_name != full_domain:
        domain_obj.domain_name = full_domain
        # domain_obj.acquired_domain = None
        domain_obj.save()

    print(f"✅ Vendor domain set: {full_domain}")

