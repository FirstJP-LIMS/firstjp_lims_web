# apps/notifications/views.py

# apps/notifications/views.py
from django.shortcuts import render
from django.contrib.auth.decorators import login_required

@login_required
def notification_inbox_view(request):
    return render(request, "laboratory/notification/inbox.html")

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .models import Notification

class NotificationListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        notifications = Notification.objects.filter(user=request.user).order_by('-created_at')[:50]
        return Response([
            {
                "id": n.id,
                "event_type": n.event_type,
                "payload": n.payload,
                "read": n.read,
                "created_at": n.created_at
            } for n in notifications
        ])

# apps/notifications/views.py
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def mark_notification_read(request, notification_id):
    try:
        notification = Notification.objects.get(id=notification_id, user=request.user)
        notification.read = True
        notification.save()
        return Response({"status": "success"})
    except Notification.DoesNotExist:
        return Response({"status": "not_found"}, status=404)
