from django.urls import path
from . import views
# from . accounts import views

urlpatterns = [
    path('', views.platform_home, name='platform_home'),
]
