
# apps/notifications/models.py
from django.db import models
from django.conf import settings
from django.utils import timezone

class Notification(models.Model):
    """
    Stores notifications for a user.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications", blank=True, null=True)
    event_type = models.CharField(max_length=100, null=True, blank=True)
    payload = models.JSONField(default=dict)  # Store arbitrary event data
    read = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Notification({self.event_type} for {self.user})"
