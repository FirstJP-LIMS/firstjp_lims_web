from django.urls import path
from . import views

app_name = "account"

urlpatterns = [
    path('register/', views.tenant_register_by_role, name='register'),

    path('login/', views.tenant_login, name='login'),
    
    path('logout/', views.tenant_logout, name='logout'),
]
