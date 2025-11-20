from django.core.mail import send_mail
from django.conf import settings

def send_vendor_onboarding_emails(vendor, user):
    """
    Sends onboarding emails:
    - To the vendor admin (confirmation)
    - To the platform admin (notification)
    """

    # Email to Vendor Admin
    vendor_subject = "Vendor Onboarding Request Received"
    vendor_message = (
        f"Hello {user.first_name},\n\n"
        f"Thank you for submitting your onboarding request for {vendor.name}.\n"
        f"Our team will review your application and contact you soon.\n\n"
        f"Regards,\n{settings.SITE_NAME} Team"
    )
    send_mail(
        vendor_subject,
        vendor_message,
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        fail_silently=False,
    )

    # Email to Platform Admin
    admin_subject = "New Vendor Onboarding Request"
    admin_message = (
        f"A new vendor has submitted an onboarding request.\n\n"
        f"Vendor Name: {vendor.name}\n"
        f"Contact Email: {vendor.contact_email}\n"
        f"Plan Type: {vendor.plan_type}\n\n"
        f"Please log in to review and approve."
    )
    send_mail(
        admin_subject,
        admin_message,
        settings.DEFAULT_FROM_EMAIL,
        [settings.PLATFORM_ADMIN_EMAIL], 
        fail_silently=False,
    )
