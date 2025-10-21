# apps/tenants/signals.py (FIXED)
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
from .models import Vendor, VendorDomain


@receiver(post_save, sender=Vendor)
def create_vendor_domain(sender, instance, created, **kwargs):
    """
    Automatically creates a full domain/subdomain for each vendor upon activation.
    """
    if instance.is_active:
        BASE_DOMAIN = settings.GLOBAL_HOSTS[0] if settings.GLOBAL_HOSTS else "localhost"
        subdomain = instance.subdomain_prefix.lower()
        full_domain = f"{subdomain}.{BASE_DOMAIN}"

        domain_obj, created_domain = VendorDomain.objects.get_or_create(
            vendor=instance,
            defaults={'domain_name': full_domain, 'is_primary': True}
        )

        if not created_domain and domain_obj.domain_name != full_domain:
            domain_obj.domain_name = full_domain
            domain_obj.save()

        print(f"✅ Vendor domain set: {full_domain}")

