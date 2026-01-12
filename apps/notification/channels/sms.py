# apps/notifications/channels/sms.py
def send_notification(event):
    phone_number = event.payload.get("user_phone")
    if not phone_number:
        return

    message = f"LIMS Alert: {event.event_type.replace('_', ' ').title()}"

    # Example using Twilio (assuming client is configured)
    # from .sms_client import twilio_client
    # twilio_client.messages.create(body=message, from_="+1234567890", to=phone_number)

    print(f"SMS to {phone_number}: {message}")  # placeholder for now

