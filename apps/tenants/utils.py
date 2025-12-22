from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from django.urls import reverse


def send_vendor_onboarding_emails(vendor, user):
    """
    Sends structured HTML onboarding emails to Vendor and Platform Admin.
    """
    # 1. Prepare Data Context
    context = {
        'first_name': user.first_name,
        'vendor_name': vendor.name,
        'vendor_email': vendor.contact_email,
        'plan_type': vendor.plan_type,
        'site_name': settings.SITE_NAME,
    }

    # 2. Email to Vendor Admin
    send_html_email(
        subject="Vendor Onboarding Request Received",
        template_name='emails/onboarding/vendor_notification.html',
        context=context,
        recipient_list=[user.email]
    )

    # 3. Email to Platform Admin
    send_html_email(
        subject="New Vendor Onboarding Request",
        template_name='emails/onboarding/admin_notification.html',
        context=context,
        recipient_list=[settings.DEFAULT_FROM_EMAIL]
    )

def send_html_email(subject, template_name, context, recipient_list):
    """
    Helper function to handle HTML rendering and sending.
    """
    html_content = render_to_string(template_name, context)
    text_content = strip_tags(html_content)  # Fallback for old email clients

    email = EmailMultiAlternatives(
        subject=subject,
        body=text_content,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=recipient_list
    )
    email.attach_alternative(html_content, "text/html")
    email.send(fail_silently=False)


"""
Send domain details to tenant
"""
def send_vendor_activation_email(vendor):
    domain_obj = vendor.get_primary_domain()
    if not domain_obj:
        return

    protocol = 'https' if not settings.DEBUG else 'http'
    domain_name = domain_obj.domain_name
    login_url = f"{protocol}://{domain_name}{reverse('account:login')}"

    subject = "Your Lab Domain Is Now Active 🎉"
    context = {
        'vendor_name': vendor.name,
        'vendor_email': vendor.contact_email,
        'domain_name': domain_name,
        'login_url': login_url,
        'protocol': protocol,
        'domain': settings.SITE_NAME, # Your main app domain for the logo
        'platform_name': settings.SITE_NAME,
    }

    html_content = render_to_string('emails/onboarding/domain_activation.html', context)
    text_content = strip_tags(html_content)

    email = EmailMultiAlternatives(
        subject=subject,
        body=text_content,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[vendor.contact_email],
    )
    email.attach_alternative(html_content, "text/html")
    email.send()


# from django.core.mail import send_mail
# from django.conf import settings

# def send_vendor_onboarding_emails(vendor, user):
#     """
#     Sends onboarding emails:
#     - To the vendor admin (confirmation)
#     - To the platform admin (notification)
#     """

#     # Email to Vendor Admin
#     vendor_subject = "Vendor Onboarding Request Received"
#     vendor_message = (
#         f"Hello {user.first_name},\n\n"
#         f"Thank you for submitting your onboarding request for {vendor.name}.\n"
#         f"Our team will review your application and contact you soon.\n\n"
#         f"Regards,\n{settings.SITE_NAME} Team"
#     )
#     send_mail(
#         vendor_subject,
#         vendor_message,
#         settings.DEFAULT_FROM_EMAIL,
#         [user.email],
#         fail_silently=False,
#     )

#     # Email to Platform Admin
#     admin_subject = "New Vendor Onboarding Request"
#     admin_message = (
#         f"A new vendor has submitted an onboarding request.\n\n"
#         f"Vendor Name: {vendor.name}\n"
#         f"Contact Email: {vendor.contact_email}\n"
#         f"Plan Type: {vendor.plan_type}\n\n"
#         f"Please log in to review and approve."
#     )
#     send_mail(
#         admin_subject,
#         admin_message,
#         settings.DEFAULT_FROM_EMAIL,
#         [settings.PLATFORM_ADMIN_EMAIL], 
#         fail_silently=False,
#     )


