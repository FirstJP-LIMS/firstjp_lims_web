# apps/notifications/channels/email.py
from django.core.mail import send_mail
from django.template.loader import render_to_string

def send_notification(event):
    """
    Send email notifications based on event type and payload
    """
    user_email = event.payload.get("user_email")
    if not user_email:
        return

    subject = f"LIMS Notification: {event.event_type.replace('_', ' ').title()}"
    message = render_to_string(f"notifications/{event.event_type}.txt", {"payload": event.payload})

    send_mail(
        subject,
        message,
        "noreply@lims.com",
        [user_email],
        fail_silently=False
    )
