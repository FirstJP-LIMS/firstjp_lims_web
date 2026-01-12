
# apps/notifications/engine.py
from typing import List
from .domain_events import DomainEvent
from .channels import websocket, email, sms
from .preferences.models import NotificationPreference
from .models import Notification

# Celery task import
from .tasks import send_email_task, send_sms_task

def dispatch_event(event: DomainEvent, channels: List[str] = None):
    """
    Dispatch a domain event to multiple delivery channels
    respecting user preferences.
    """
    # Default channels
    if channels is None:
        channels = ["websocket", "email", "sms"]

    # Determine user preferences
    user_id = event.payload.get("user_id")
    if user_id:
        try:
            prefs = NotificationPreference.objects.get(user_id=user_id)
            if prefs.in_app_enabled:
                # Save to database for history
                Notification.objects.create(
                    user_id=user_id,
                    event_type=event.event_type,
                    payload=event.payload
                )
                websocket.send_notification(event)
        except NotificationPreference.DoesNotExist:
            prefs = NotificationPreference(email_enabled=True, sms_enabled=True, in_app_enabled=True)
    else:
        # If no specific user, assume all channels enabled
        prefs = NotificationPreference(email_enabled=True, sms_enabled=True, in_app_enabled=True)

    # Dispatch channels according to preferences
    if "websocket" in channels and prefs.in_app_enabled:
        websocket.send_notification(event)  # synchronous for realtime

    if "email" in channels and prefs.email_enabled:
        send_email_task.delay(event.__dict__)  # async via Celery

    if "sms" in channels and prefs.sms_enabled:
        send_sms_task.delay(event.__dict__)  # async via Celery


# Change to this later        
# # apps/notifications/engine.py
# from typing import List
# from .domain_events import DomainEvent
# from .channels import websocket, email, sms
# from .preferences.models import NotificationPreference
# from .tasks import send_email_task, send_sms_task

# def dispatch_event(event: DomainEvent, channels: List[str] = None):
#     """
#     Dispatch a domain event to multiple delivery channels,
#     respecting the user's notification preferences.
#     """
#     if channels is None:
#         channels = ["websocket", "email", "sms"]

#     user_id = event.payload.get("user_id")
#     prefs = None

#     if user_id:
#         try:
#             prefs = NotificationPreference.objects.get(user_id=user_id)
#         except NotificationPreference.DoesNotExist:
#             # Default preferences if none exist
#             prefs = NotificationPreference(email_enabled=True, sms_enabled=True, in_app_enabled=True)
#     else:
#         # System-wide notifications
#         prefs = NotificationPreference(email_enabled=True, sms_enabled=True, in_app_enabled=True)

#     # Dispatch channels according to user preferences
#     if "websocket" in channels and prefs.in_app_enabled:
#         websocket.send_notification(event)  # synchronous

#     if "email" in channels and prefs.email_enabled:
#         send_email_task.delay(event.__dict__)  # async

#     if "sms" in channels and prefs.sms_enabled:
#         send_sms_task.delay(event.__dict__)  # async



# apps/notifications/engine.py
# from typing import List
# from .domain_events import DomainEvent
# from .channels import websocket, email, sms

# CHANNEL_MAP = {
#     "websocket": websocket.send_notification,
#     "email": email.send_notification,
#     "sms": sms.send_notification
# }

# def dispatch_event(event: DomainEvent, channels: List[str] = None):
#     """
#     Dispatch a domain event to multiple delivery channels.
#     """
#     if channels is None:
#         channels = ["websocket", "email", "sms"]

#     for channel in channels:
#         handler = CHANNEL_MAP.get(channel)
#         if handler:
#             handler(event)

