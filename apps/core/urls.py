from django.urls import path
from . import views


urlpatterns = [
    path('', views.platform_home, name='platform_home'),
    path('firstjp/', views.firstjp_index, name='firstjp_index'),
    path('firstjp/payments/', views.firstjp_payments, name='firstjp_payments'),
    path('firstjp/admin/', views.firstjp_admin, name='firstjp_admin'),
]
