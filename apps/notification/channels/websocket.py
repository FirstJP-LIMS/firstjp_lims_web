# apps/notifications/channels/websocket.py
import json
from channels.generic.websocket import AsyncWebsocketConsumer
# apps/notifications/channels/websocket.py

# apps/notifications/channels/websocket.py
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from apps.notification.models import Notification
from ..preferences.models import NotificationPreference
import json


class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]
        if self.user.is_authenticated:
            # Create a unique group name for this user
            self.group_name = f"user_{self.user.id}_notifications"

            await self.channel_layer.group_add(
                self.group_name,
                self.channel_name
            )
            await self.accept()
        else:
            await self.close()

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )

    # This method is called when the engine sends a message to the group
    async def send_notification(self, event):
        await self.send(text_data=json.dumps(event["payload"]))
        


def send_notification(event):
    """
    Send event via WebSocket and save it for history.
    """
    user_id = event.payload.get("user_id")
    if not user_id:
        return

    # Check user preferences
    try:
        prefs = NotificationPreference.objects.get(user_id=user_id)
        if not prefs.in_app_enabled:
            return
    except NotificationPreference.DoesNotExist:
        pass  # Default allow

    # Save notification
    Notification.objects.create(
        user_id=user_id,
        event_type=event.event_type,
        payload=event.payload
    )

    # Send via WebSocket
    channel_layer = get_channel_layer()
    group_name = f"user_{user_id}"
    async_to_sync(channel_layer.group_send)(
        group_name,
        {
            "type": "lims_notification",
            "message": json.dumps({
                "id": event.id,
                "type": event.event_type,
                "payload": event.payload,
                "timestamp": str(event.timestamp)
            })
        }
    )

# import json
# from asgiref.sync import async_to_sync
# from channels.layers import get_channel_layer

# def send_notification(event):
#     """
#     Sends event to websocket groups.
#     """
#     channel_layer = get_channel_layer()
#     group_name = f"user_{event.payload.get('user_id', 'all')}"  # or lab/user specific

#     async_to_sync(channel_layer.group_send)(
#         group_name,
#         {
#             "type": "lims.notification",
#             "message": json.dumps({
#                 "id": event.id,
#                 "type": event.event_type,
#                 "payload": event.payload,
#                 "timestamp": str(event.timestamp)
#             })
#         }
#     )
