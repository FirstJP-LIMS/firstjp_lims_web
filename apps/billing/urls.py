from django.urls import path
# from . import views
from .views import billing_task, payment_gateway, invoice_receipt, pricelist, insurance_provider, corporate_client

app_name = 'billing'

"""
Update with new paths: 
invoice -- draft_invoices, overdue_invoices, 
revenue report, aging report, tax report,
settings, how it works... 
"""

urlpatterns = [
    # Dashboard
    path('dashboard/', billing_task.BillingDashboardView.as_view(), name='dashboard'),
    
    # Price Lists
    path('pricelists/', pricelist.pricelist_list_view, name='pricelist_list'),
    path('pricelists/create/', pricelist.pricelist_create_view, name='pricelist_create'),
    path('pricelists/<int:pk>/', pricelist.pricelist_detail_view, name='pricelist_detail'),
    path('pricelists/<int:pk>/edit/', pricelist.pricelist_update_view, name='pricelist_update'),
    path('pricelists/<int:pk>/delete/', pricelist.pricelist_delete_view, name='pricelist_delete'),
    path('pricelists/<int:pk>/toggle-active/', pricelist.pricelist_toggle_active_view, name='pricelist_toggle_active'), # To be used in details to set active and inactive...

    # Billing Info
    path('billings/', billing_task.billing_list_view, name='billing_list'),
    path('billings/create/', billing_task.billing_create_view, name='billing_create'),
    path('billings/<int:pk>/edit/', billing_task.billing_update_view, name='billing_update'),
    path('billings/<int:pk>/recalculate/', billing_task.billing_recalculate_view, name='billing_recalculate'),
    path('billings/<int:pk>/print/', billing_task.billing_print_view, name='billing_print'),
    path('billings/summary/', billing_task.billing_summary_view, name='billing_summary'),
    path('billings/bulk-action/', billing_task.billing_bulk_action_view, name='billing_bulk_action'),
    
    path('billings/<int:pk>/detail/', billing_task.billing_detail_view, name='billing_detail'),

    # Payment Actions
    path('billing/<int:pk>/authorize/', billing_task.authorize_billing_view, name='authorize_billing'),
    path('billing/<int:pk>/waive/', billing_task.waive_billing_view, name='waive_billing'),
    path('billing/<int:pk>/confirm-payment/', billing_task.confirm_payment_view, name='confirm_payment'),
    
    # Payment Gateway (for future implementation)
    # path('billing/<int:pk>/pay-online/', views.initiate_online_payment, name='pay_online'),
    # path('payment/callback/', views.payment_gateway_callback, name='payment_callback'),

 
    # Payments
    path('billings/<int:billing_pk>/payment/', billing_task.PaymentCreateView.as_view(), name='payment_create'),
    


    # Insurance Providers
    path('insurance/', insurance_provider.insurance_list_view, name='insurance_list'),
    path('insurance/create/', insurance_provider.insurance_create_view, name='insurance_create'),
    path('insurance/<int:pk>/', insurance_provider.insurance_detail_view, name='insurance_detail'),
    path('insurance/<int:pk>/edit/', insurance_provider.insurance_update_view, name='insurance_update'),
    path('insurance/<int:pk>/delete/', insurance_provider.insurance_delete_view, name='insurance_delete'),
    path('insurance/<int:pk>/toggle-active/', insurance_provider.insurance_toggle_active_view, name='insurance_toggle_active'),
    path('insurance/<int:pk>/financial-report/', insurance_provider.insurance_financial_report_view, name='insurance_financial_report'),
    
    # Bulk actions
    path('insurance/bulk-deactivate/', insurance_provider.insurance_bulk_deactivate_view, name='insurance_bulk_deactivate'),



    # Corporate Clients
    path('corporate/', corporate_client.corporate_list_view, name='corporate_list'),
    path('corporate/create/', corporate_client.corporate_create_view, name='corporate_create'),
    path('corporate/<int:pk>/', corporate_client.corporate_detail_view, name='corporate_detail'),
    path('corporate/<int:pk>/edit/', corporate_client.corporate_update_view, name='corporate_update'),
    path('corporate/<int:pk>/delete/', corporate_client.corporate_delete_view, name='corporate_delete'),
    path('corporate/<int:pk>/toggle-active/', corporate_client.corporate_toggle_active_view, name='corporate_toggle_active'),
    path('corporate/<int:pk>/employee-report/', corporate_client.corporate_employee_report_view, name='corporate_employee_report'),
    path('corporate/<int:pk>/financial-report/', corporate_client.corporate_financial_report_view, name='corporate_financial_report'),
        
    # # Invoices
    path('invoices/', invoice_receipt.invoice_list, name='invoice_list'),
    path('invoices/create/', invoice_receipt.invoice_create, name='invoice_create'),
    path('invoices/<int:pk>/', invoice_receipt.invoice_detail, name='invoice_detail'),

    # Invoice Payment
    path('invoices/<int:invoice_pk>/payments/create/', 
         invoice_receipt.invoice_payment_create, 
         name='invoice_payment_create'),
    
    # PDF Generation - Download
    path('invoices/<int:invoice_pk>/pdf/', 
         invoice_receipt.generate_invoice_pdf_view, 
         name='invoice_pdf_download'),
    
    path('invoices/<int:invoice_pk>/pdf/preview/', 
         invoice_receipt.preview_invoice_pdf_view, 
         name='invoice_pdf_preview'),
    
    path('payments/<int:payment_pk>/receipt/pdf/', 
         invoice_receipt.generate_receipt_pdf_view, 
         name='receipt_pdf_download'),
    
    path('payments/<int:payment_pk>/receipt/pdf/preview/', 
         invoice_receipt.preview_receipt_pdf_view, 
         name='receipt_pdf_preview'),
    
    # Email Invoice & Receipt
    path('invoices/<int:invoice_pk>/email/', 
         invoice_receipt.email_invoice_view, 
         name='email_invoice'),
    
    path('payments/<int:payment_pk>/receipt/email/', 
         invoice_receipt.email_receipt_view, 
         name='email_receipt'),
    
    # Print View
    path('invoices/<int:invoice_pk>/print/', 
         invoice_receipt.print_invoice_view, 
         name='invoice_print'),



    # path('invoices/<int:invoice_pk>/pdf/', billing_task.GenerateInvoicePDFView.as_view(), name='generate_invoice_pdf'),
    # Reports
    path('reports/', billing_task.BillingReportView.as_view(), name='reports'),
]

 