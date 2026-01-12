from django.urls import path
# from . import views
from .views import profile, test_request

app_name = "patient"

urlpatterns = [
    path("", profile.patient_dashboard, name="patient_dashboard"),

    # profile 
    path("profile/", profile.patient_profile_view, name="profile_view"),
    path("update/", profile.patient_profile_edit, name="profile_edit"),

    # Order - Request
    path('tests/', test_request.patient_test_catalog, name='test_catalog'),
    path('orders/new/', test_request.patient_create_order, name='create_order'),
    path('orders/', test_request.patient_order_list, name='orders_list'),
    path('orders/<str:request_id>/', test_request.patient_order_detail, name='order_detail'),

    # Results
    path('results/<str:request_id>/', test_request.patient_view_results, name='view_results'),
    path('results/<str:request_id>/download/', test_request.patient_download_results, name='download_results'),

]
