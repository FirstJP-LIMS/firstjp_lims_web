from django.urls import path
from . import views

app_name = "patient"

urlpatterns = [
    path("", views.patient_dashboard, name="patient_dashboard"),

    # profile 
    path("profile/", views.patient_profile_view, name="profile_view"),
    path("update/", views.patient_profile_edit, name="profile_edit"),

    # Order - Request
    path('tests/', views.patient_test_catalog, name='test_catalog'),
    path('orders/new/', views.patient_create_order, name='create_order'),
    path('orders/', views.patient_order_list, name='orders_list'),
    path('orders/<str:request_id>/', views.patient_order_detail, name='order_detail'),

    # Results
    path('results/<str:request_id>/', views.patient_view_results, name='view_results'),
    path('results/<str:request_id>/download/', views.patient_download_results, name='download_results'),
]

