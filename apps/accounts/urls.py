from django.urls import path
from . import views


urlpatterns = [
    path('register/', views.tenant_register, name='register'),
    path('login/', views.tenant_login, name='login'),
    path('logout/', views.tenant_logout, name='logout'),
]
