from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.mail import send_mail
from django.conf import settings
from tenants.models import Vendor


def admin_vendor_list(request):
    """Platform admin dashboard view for managing vendors."""
    pending_vendors = Vendor.objects.filter(is_active=False)
    active_vendors = Vendor.objects.filter(is_active=True)
    return render(request, "tenants/admin_vendor_dashboard.html", {
        "pending_vendors": pending_vendors,
        "active_vendors": active_vendors
    })

def activate_vendor(request, vendor_id):
    """Activate a vendor and send an activation email."""
    vendor = get_object_or_404(Vendor, pk=vendor_id)
    vendor.is_active = True
    vendor.save()

    domain = vendor.domains.first()
    send_mail(
        subject="✅ Your Lab is Now Active!",
        message=(
            f"Dear {vendor.name},\n\n"
            f"Your lab has been activated.\n"
            f"You can now log in at http://{domain.domain_name}:8000/\n\n"
            f"Regards,\nPlatform Team"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[vendor.contact_email],
    )

    messages.success(request, f"{vendor.name} has been activated and notified.")
    return redirect("admin_vendor_list")
