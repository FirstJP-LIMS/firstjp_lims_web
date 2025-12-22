from django.urls import path
from . import views

app_name = 'clinician'

urlpatterns = [
    path('dashboard/', views.clinician_dashboard, name='clinician_dashboard'),

    # profile 
    path('profile/', views.clinician_profile, name='profile'),


    # Patient...
    path('patients/search/', views.patient_search, name='patient_search'),
    path('patients/my-patients/', views.my_patients_list, name='my_patients'),
    path('patients/<str:patient_id>/', views.patient_detail, name='patient_detail'),
    path('patients/<str:patient_id>/history/', views.patient_test_history, name='patient_test_history'),
   
    # Test Ordering
    path('tests/catalog/', views.test_catalog, name='test_catalog'),
    path('tests/order/new/', views.create_test_order, name='create_test_order'),
    path('tests/order/new/<str:patient_id>/', views.create_test_order, name='create_test_order_for_patient'),

    path('tests/order/quick/<str:patient_id>/', views.quick_order_from_patient, name='quick_order'),
    
    # Order Management
    path('orders/', views.my_orders, name='my_orders'),
    path('orders/<str:request_id>/', views.test_request_detail, name='test_request_detail'),
    path('orders/bulk-action/', views.bulk_order_actions, name='bulk_order_actions'),
    path('test-request/<str:request_id>/cancel/', views.cancel_test_request, name='cancel_test_request'),
    path('test-request/<str:request_id>/download-results/', views.download_results, name='download_results'),

# Results
    path('result/', views.clinician_result_list, name="my_results"),
    path('result/<str:request_id>/', views.clinician_result_detail, name="view_result_detail"),  # Detail view
    path('result/<int:pk>/acknowledge/', views.clinician_acknowledge_result, name="acknowledge_results"),
    path('result/download/<str:request_id>/', views.download_results, name="download_results"),
    
    # Autocomplete (for AJAX)
    path('patients/autocomplete/', views.patient_autocomplete, name='patient_autocomplete'),

]

