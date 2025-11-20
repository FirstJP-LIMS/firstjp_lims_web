from django.shortcuts import render
from django.urls import path
from . import views

urlpatterns = [
    path("onboarding/", views.vendor_onboarding_view, name="vendor_onboarding"),
    # path("onboarding/success/", lambda r: render(r, "platform/onboarding/onboarding_success.html"), name="vendor_onboarding_success"),
    path("onboarding/success/", views.vendor_onboarding_success, name="vendor_onboarding_success"),
]

