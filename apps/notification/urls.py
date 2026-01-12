# apps/notifications/urls.py
from django.urls import path
from . import views

app_name = "notification"

urlpatterns = [
    # The HTML Page
    path("inbox/", views.notification_inbox_view, name="inbox"), 
    
    # Your existing API Endpoints
    path("api/", views.NotificationListView.as_view(), name="api_list"),
    path("api/<int:notification_id>/read/", views.mark_notification_read, name="api_mark_read"),
]


# # urls.py
# from django.urls import path
# from .views import NotificationListView, mark_notification_read

# app_name = "notification"

# urlpatterns = [
#     path("api/notifications/", NotificationListView.as_view(), name="notifications_list"),
#     path("api/notifications/<int:notification_id>/read/", mark_notification_read, name="notification_mark_read"),
# ]

