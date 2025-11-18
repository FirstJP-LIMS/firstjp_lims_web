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

    # test request
    path('test-requests/create/', views.test_request_create, name='create_test_request'),

    path('test-requests/', views.test_request_list, name='test_request_list'),

    path('requests/<int:pk>/update/', views.test_request_update, name='request_update'),

    path('requests/<int:pk>/detail/', views.test_request_detail, name='request_detail'),
    
    path('requests/<int:pk>/delete/', views.test_request_delete, name='delete_request'),

    # download Test Request 
    path('test-request/<int:pk>/download/', views.download_test_request, name='download_test_request'),
    
    path("requests/download/blank/", views.download_test_request, {"blank": True}, name="download_blank_test_request"
    ),

    # examination
    path('examination/samples/', views.sample_examination_list, name='sample-exam-list'),

    path('examination/sample/<str:sample_id>/', views.sample_examination_detail, name='sample-exam-detail'),

   # Test Assignment Management
# ===== Test Assignment List & Management =====
    path(
        'assignments/',
        views.test_assignment_list,
        name='test_assignment_list'
    ),
    
    path(
        'assignment/<int:assignment_id>/',
        views.test_assignment_detail,
        name='test_assignment_detail'
    ),
    
    # ===== Quick Actions (AJAX) =====
    path(
        'assignment/<int:assignment_id>/quick-send/',
        views.quick_send_to_instrument,
        name='quick_send_to_instrument'
    ),
    
    path(
        'assignments/stats/',
        views.assignment_quick_stats,
        name='assignment_quick_stats'
    ),
    
    # ===== Bulk Actions =====
    path(
        'assignments/bulk-send/',
        views.bulk_send_to_instrument,
        name='bulk_send_to_instrument'
    ),
    
    path(
        'assignments/bulk-assign-instrument/',
        views.bulk_assign_instrument,
        name='bulk_assign_instrument'
    ),
    
    path(
        'assignments/bulk-assign-technician/',
        views.bulk_assign_technician,
        name='bulk_assign_technician'
    ),
    
    # ===== Export =====
    path(
        'assignments/export-csv/',
        views.export_assignments_csv,
        name='export_assignments_csv'
    ),
    
    # ===== Instrument Integration (from previous) =====
    path(
        'assignment/<int:assignment_id>/send-to-instrument/',
        views.send_to_instrument,
        name='send_to_instrument'
    ),
    
    path(
        'assignment/<int:assignment_id>/fetch-result/',
        views.fetch_result_from_instrument,
        name='fetch_result_from_instrument'
    ),
    
    # ===== Manual Result Entry =====
    path(
        'assignment/<int:assignment_id>/enter-manual-result/',
        views.enter_manual_result,
        name='enter_manual_result'
    ),
    
    # ===== Result Verification & Release =====
    path(
        'assignment/<int:assignment_id>/verify/',
        views.verify_result,
        name='verify_result'
    ),
    
    path(
        'assignment/<int:assignment_id>/release/',
        views.release_result,
        name='release_result'
    ),
    
    # ===== Instrument Status =====
    path(
        'instrument/<int:instrument_id>/status/',
        views.instrument_status_check,
        name='instrument_status_check'
    ),
    
    # # ===== Dashboard =====
    # path(
    #     'pending-results/',
    #     views.pending_results_dashboard,
    #     name='pending_results_dashboard'
    # ),
]

