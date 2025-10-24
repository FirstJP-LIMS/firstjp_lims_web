from django.urls import path
from ..crm import views


urlpatterns = [
    path('dashboard/', views.dashboard, name='vendor_dashboard'),
    path('assistants/', views.lab_assistants, name='lab_assistants'),
    path('profile/', views.profile, name='vendor_profile'),
]
