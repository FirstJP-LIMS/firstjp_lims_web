from django.urls import path
from . import views


urlpatterns = [
    # Dashboard
    path('dashboard/', views.dashboard, name='vendor_dashboard'),
    path('assistants/', views.lab_assistants, name='lab_assistants'),
    path('profile/', views.profile, name='vendor_profile'),

    # VendorTest CRUD URLs
    path("vendor-tests/", views.vendor_tests_list, name="vendor_tests_list"),
    path("vendor-tests/add/", views.vendor_test_create, name="vendor_test_create"),
    path("vendor-tests/<slug:slug>/edit/", views.vendor_test_edit, name="vendor_test_edit"),
    path("vendor-tests/<slug:slug>/delete/", views.vendor_test_delete, name="vendor_test_delete"),

    # Patient add
    path('patients/', views.patient_list, name='patient_list'),
    path('patients/add/', views.add_patient, name='add_patient'),

    # test request create
    path('test-requests/create/', views.create_test_request, name='create_test_request'),
    path('test-requests/', views.test_request_list, name='test_request_list'),
    path('requests/<int:pk>/', views.test_request_detail, name='request_detail'),
]

