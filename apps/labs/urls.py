from django.urls import path
from . import views

app_name = "labs"

urlpatterns = [
    # Dashboard
    path('dashboard/', views.dashboard, name='vendor_dashboard'),
    path('assistants/', views.lab_assistants, name='lab_assistants'),
    path('profile/', views.profile, name='vendor_profile'),

    # VendorTest CRUD URLs
    # path("vendor-tests/", views.vendor_tests_list, name="vendor_tests_list"),
    # path("vendor-tests/add/", views.vendor_test_create, name="vendor_test_create"),
    # path("vendor-tests/<slug:slug>/edit/", views.vendor_test_edit, name="vendor_test_edit"),
    # path("vendor-tests/<slug:slug>/delete/", views.vendor_test_delete, name="vendor_test_delete"),

    path("departments/", views.department_list, name="department_list"),
    path("departments/create/", views.department_create, name="department_create"),
    path("departments/<int:pk>/update/", views.department_update, name="department_update"),
    path("departments/<int:pk>/delete/", views.department_delete, name="department_delete"),

    # Tests
    path("tests/", views.test_list, name="test_list"),
    path("tests/create/", views.test_create, name="test_create"),
    path("tests/<int:pk>/update/", views.test_update, name="test_update"),
    path("tests/<int:pk>/delete/", views.test_delete, name="test_delete"),


    # Patient add
    path('patients/', views.patient_list, name='patient_list'),
    path('patients/add/', views.add_patient, name='add_patient'),

    # test request create
    path('test-requests/create/', views.create_test_request, name='create_test_request'),
    path('test-requests/', views.test_request_list, name='test_request_list'),
    path('requests/<int:pk>/', views.test_request_detail, name='request_detail'),
]

