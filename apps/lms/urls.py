from django.urls import path, include
from . import views

app_name = 'lms'

urlpatterns = [
    path('', views.learning_landing_view, name="index"),
    path('', views.lms_dashboard, name="lms_dashboard"),
]

