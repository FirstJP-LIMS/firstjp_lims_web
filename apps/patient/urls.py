from django.urls import path
from . import views

app_name = "patient"

urlpatterns = [
    path("", views.patient_dashboard, name="patient_dashboard"),
    path("view/", views.patient_profile_view, name="profile_view"),
    path("update/", views.patient_profile_edit, name="profile_edit"),
]

