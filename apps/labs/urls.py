from django.urls import path

from .views import (
    # Core system views (Dashboard, Profiles, Staff)
    base,
    sample_mgt,
    
    # Configuration (Departments, Test definitions)
    setup, 
    
    # Document generation (PDFs, specialized downloads)
    downloads, 
    
    # External hardware & Automation
    instruments,
    
    # Pre-Analytical (Client/Doctor orders)
    test_requests, 
    
    # Pre-Analytical (Accessioning & Processing)
    test_assignments,
    
    # Post-Analytical (Entry, Verification, Release)
    test_results,
    
    # Clinical Governance (QC Lots, Charts, LJ-Graphs)
    qty_control,
    
    # export_mail, # Currently disabled - handles automated dispatch

    # Pateint
    patient,
)

app_name = "labs"

urlpatterns = [
    # dashboard
    path('dashboard/', base.dashboard, name='vendor_dashboard'),
    path('assistants/', base.lab_assistants, name='lab_assistants'),
    path('profile/', base.profile, name='vendor_profile'),

    # Patient Seen in the Lab
    path('patient/', patient.PatientListView.as_view(), name="patient_list"),
    path('patient-detail/<int:pk>/', patient.PatientDetailView.as_view(), name="patient_detail"),

    # Lab Setup
    # Department Crud
    path("departments/", setup.department_list, name="department_list"),
    path("departments/create/", setup.department_create, name="department_create"),
    path("departments/<int:pk>/update/", setup.department_update, name="department_update"),
    path("departments/<int:pk>/delete/", setup.department_delete, name="department_delete"),

    # Test Crud
    path("tests/", setup.test_list, name="test_list"),
    path("tests/create/", setup.test_create, name="test_create"),
    path("tests/<int:pk>/update/", setup.test_update, name="test_update"),
    path("tests/<int:pk>/delete/", setup.test_delete, name="test_delete"),

    # Test request
    path('test-requests/create/', test_requests.test_request_create, name='create_test_request'),
    path('test-requests/', test_requests.test_request_list, name='test_request_list'),
    path('requests/<uuid:pk>/update/', test_requests.test_request_update, name='request_update'),
    path('requests/<uuid:pk>/detail/', test_requests.test_request_detail, name='request_detail'),
    path('requests/<uuid:pk>/delete/', test_requests.test_request_delete, name='delete_request'),

    # download Test Request 
    path('test-request/<uuid:pk>/download/', downloads.download_test_request, name='download_test_request'),
    path("requests/download/blank/", downloads.download_test_request, {"blank": True}, name="download_blank_test_request"),

    # examination
    path('examination/samples/', sample_mgt.sample_examination_list, name='sample-exam-list'),

    # 🆕 Sample Collection URLs
    path('samples/collect/<uuid:billing_pk>/', sample_mgt.collect_sample_view, name='collect_sample'),

    path('examination/sample/<str:sample_id>/', sample_mgt.sample_examination_detail, name='sample-exam-detail'),

    # Bulk verification
    path('samples/bulk/verify/', sample_mgt.sample_bulk_verify, name='sample-bulk-verify'),
    
    # Admin override
    path('samples/<str:sample_id>/verify-override/', sample_mgt.sample_verify_override_payment,  name='sample-verify-override'),

    # path('samples/quick-collect/<int:billing_pk>/', views.quick_collect_sample_view, name='quick_collect_sample'),
    


    # ===== Test Assignment =====
    path('assignments/', test_assignments.test_assignment_list, name='test_assignment_list'),

    path('assignment/<uuid:assignment_id>/', test_assignments.test_assignment_detail, name='test_assignment_detail'),


    # Result Management URLs
    # ===== Manual Result Entry =====

    path(
        'assignment/<uuid:assignment_id>/enter-result/', 
         test_results.enter_manual_result, 
         name='enter_manual_test_result'
    ),
    
    path(
        "result/<uuid:result_id>/update/",
        test_results.update_manual_result,
        name="update_manual_test_result",
    ),

    path(
        'results/',
        test_results.result_list, 
        name='result_list'
        ),
    
    path('result/<uuid:result_id>/', test_results.result_detail, name='result_detail'),
    # path('result/<int:result_id>/', test_results.result_detail, name='result_detail'),

    path('result/<uuid:result_id>/amend/', test_results.amend_result, name='amend_result'),

    path('result/<uuid:result_id>/verify/', test_results.verify_result, name='verify_result'),

    path('result/<uuid:result_id>/release/', test_results.release_result, name='release_result'),

    path('result/<uuid:result_id>/download/', test_results.download_result_pdf, name='download_result_pdf'),


    # ===== Quick Instrument Assignment =====
    # ===== Bulk Actions =====
    path('assignment/<uuid:assignment_id>/assign-instrument/', instruments.assign_instrument, name='assign_instrument'),
    path('assignments/bulk-assign-instrument/', instruments.bulk_assign_instrument, name='bulk_assign_instrument'),    
    path('assignments/auto_assign_instruments/', instruments.auto_assign_instruments, name='auto_assign_instruments'),
    # Unclear
    path('assignments/bulk-assign-technician/', instruments.bulk_assign_technician, name='bulk_assign_technician'),
    path('assignments/bulk-send/', instruments.bulk_send_to_instrument, name='bulk_send_to_instrument'),
    

    path('assignments/stats/', test_assignments.assignment_quick_stats,name='assignment_quick_stats'),
    # ===== Instrument Integration (from previous) =====
    path('assignment/<uuid:assignment_id>/send-to-instrument/',
        instruments.send_to_instrument,
        name='send_to_instrument'
    ),
    
    path(
        'assignment/<uuid:assignment_id>/fetch-result/',
        instruments.fetch_result_from_instrument,
        name='fetch_result_from_instrument'
    ),

    # ===== Instrument Status =====
    path(
        'instrument/<int:instrument_id>/status/',
        instruments.instrument_status_check,
        name='instrument_status_check'
    ),
    



    # ===== Quick Actions (AJAX) =====
    # path('assignment/<int:assignment_id>/quick-send/', views.quick_send_to_instrument, name='quick_send_to_instrument'),

    
    
    # ===== Export =====
    path(
        'assignments/export-csv/',
        downloads.export_assignments_csv,
        name='export_assignments_csv'
    ),
    
    # ==== Quality Control ====
    path('qc/lots/', qty_control.qc_lot_list, name='qclot_list'),
    path('qc/lots/create/', qty_control.qc_lot_create, name='qclot_create'),
    path('qc/lots/<int:pk>/edit/', qty_control.qc_lot_edit, name='qclot_edit'),
    path('qc/lots/<int:pk>/toggle/', qty_control.qclot_toggle_active, name='qclot_toggle_active'),
    path('qc/lots/<int:pk>/delete/', qty_control.qclot_delete, name='qclot_delete'),

    path("qc/entry/", qty_control.qc_entry_view, name="qc_entry"),
    path("qc/results/", qty_control.qc_results_list, name="qc_results_list"),
    path("qc/results/<int:pk>/", qty_control.qc_result_detail, name="qc_result_detail"),

    # Levey-Jennings Chart
    path("qc/chart/<int:qc_lot_id>/", qty_control.levey_jennings_chart, name="levey_jennings_chart"),
    
    path("qc/chart/data/<int:qc_lot_id>/", qty_control.levey_jennings_data, name="levey_jennings_data"),

    path("qc/monthly/", qty_control.qc_monthly_report, name="qc_monthly_report"),
    path("qc/dashboard/", qty_control.qc_dashboard, name="qc_dashboard")

]

