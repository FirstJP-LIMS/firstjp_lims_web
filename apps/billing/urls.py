from django.urls import path
from . import views

app_name = 'billing'

"""
Update with new paths: 
invoice -- draft_invoices, overdue_invoices, 
revenue report, aging report, tax report,
settings, how it works... 
"""

urlpatterns = [
    # Dashboard
    path('dashboard/', views.BillingDashboardView.as_view(), name='dashboard'),
    
    # Price Lists
    path('pricelists/', views.pricelist_list_view, name='pricelist_list'),
    path('pricelists/create/', views.pricelist_create_view, name='pricelist_create'),
    path('pricelists/<int:pk>/', views.pricelist_detail_view, name='pricelist_detail'),
    path('pricelists/<int:pk>/edit/', views.pricelist_update_view, name='pricelist_update'),
    path('pricelists/<int:pk>/delete/', views.pricelist_delete_view, name='pricelist_delete'),
    path('pricelists/<int:pk>/toggle-active/', views.pricelist_toggle_active_view, name='pricelist_toggle_active'), # To be used in details to set active and inactive...
        
    # Insurance Providers
    path('insurance/', views.insurance_list_view, name='insurance_list'),
    path('insurance/create/', views.insurance_create_view, name='insurance_create'),
    path('insurance/<int:pk>/', views.insurance_detail_view, name='insurance_detail'),
    path('insurance/<int:pk>/edit/', views.insurance_update_view, name='insurance_update'),
    path('insurance/<int:pk>/delete/', views.insurance_delete_view, name='insurance_delete'),
    path('insurance/<int:pk>/toggle-active/', views.insurance_toggle_active_view, name='insurance_toggle_active'),
    path('insurance/<int:pk>/financial-report/', views.insurance_financial_report_view, name='insurance_financial_report'),
    
    # Bulk actions
    path('insurance/bulk-deactivate/', views.insurance_bulk_deactivate_view, name='insurance_bulk_deactivate'),



    # Corporate Clients
    path('corporate/', views.corporate_list_view, name='corporate_list'),
    path('corporate/create/', views.corporate_create_view, name='corporate_create'),
    path('corporate/<int:pk>/', views.corporate_detail_view, name='corporate_detail'),
    path('corporate/<int:pk>/edit/', views.corporate_update_view, name='corporate_update'),
    path('corporate/<int:pk>/delete/', views.corporate_delete_view, name='corporate_delete'),
    path('corporate/<int:pk>/toggle-active/', views.corporate_toggle_active_view, name='corporate_toggle_active'),
    path('corporate/<int:pk>/employee-report/', views.corporate_employee_report_view, name='corporate_employee_report'),
    path('corporate/<int:pk>/financial-report/', views.corporate_financial_report_view, name='corporate_financial_report'),
        
    # Billing Information
    path('billings/', views.billing_list_view, name='billing_list'),
    path('billings/create/', views.billing_create_view, name='billing_create'),
    path('billings/<int:pk>/', views.billing_detail_view, name='billing_detail'),
    path('billings/<int:pk>/edit/', views.billing_update_view, name='billing_update'),
    path('billings/<int:pk>/recalculate/', views.billing_recalculate_view, name='billing_recalculate'),
    path('billings/<int:pk>/print/', views.billing_print_view, name='billing_print'),
    path('billings/summary/', views.billing_summary_view, name='billing_summary'),
    path('billings/bulk-action/', views.billing_bulk_action_view, name='billing_bulk_action'),

 
    # Payments
    path('billings/<int:billing_pk>/payment/', views.PaymentCreateView.as_view(), name='payment_create'),
    path('payments/<int:payment_pk>/receipt/', views.GenerateReceiptPDFView.as_view(), name='generate_receipt'),
    
    # # Invoices
    # path('invoices/', views.InvoiceListView.as_view(), name='invoice_list'),
    # path('invoices/create/', views.InvoiceCreateView.as_view(), name='invoice_create'),
    # path('invoices/<int:pk>/', views.InvoiceDetailView.as_view(), name='invoice_detail'),

    # path('invoices/<int:invoice_pk>/payment/', views.InvoicePaymentCreateView.as_view(), name='invoice_payment_create'),

    path('invoices/', views.invoice_list, name='invoice_list'),
    path('invoices/create/', views.invoice_create, name='invoice_create'),
    path('invoices/<int:pk>/', views.invoice_detail, name='invoice_detail'),
    path('invoices/<int:invoice_pk>/payments/create/', 
         views.invoice_payment_create, 
         name='invoice_payment_create'),


        # Invoice URLs
    # path('invoices/', views.invoice_list, name='invoice_list'),
    # path('invoices/create/', views.invoice_create, name='invoice_create'),
    # path('invoices/<int:pk>/', views.invoice_detail, name='invoice_detail'),
    
    # Invoice Payment
    path('invoices/<int:invoice_pk>/payments/create/', 
         views.invoice_payment_create, 
         name='invoice_payment_create'),
    
    # PDF Generation - Download
    path('invoices/<int:invoice_pk>/pdf/', 
         views.generate_invoice_pdf_view, 
         name='invoice_pdf_download'),
    
    path('invoices/<int:invoice_pk>/pdf/preview/', 
         views.preview_invoice_pdf_view, 
         name='invoice_pdf_preview'),
    
    path('payments/<int:payment_pk>/receipt/pdf/', 
         views.generate_receipt_pdf_view, 
         name='receipt_pdf_download'),
    
    path('payments/<int:payment_pk>/receipt/pdf/preview/', 
         views.preview_receipt_pdf_view, 
         name='receipt_pdf_preview'),
    
    # Email Invoice & Receipt
    path('invoices/<int:invoice_pk>/email/', 
         views.email_invoice_view, 
         name='email_invoice'),
    
    path('payments/<int:payment_pk>/receipt/email/', 
         views.email_receipt_view, 
         name='email_receipt'),
    
    # Print View
    path('invoices/<int:invoice_pk>/print/', 
         views.print_invoice_view, 
         name='invoice_print'),



    # path('invoices/<int:invoice_pk>/pdf/', views.GenerateInvoicePDFView.as_view(), name='generate_invoice_pdf'),
    # Reports
    path('reports/', views.BillingReportView.as_view(), name='reports'),
]

 