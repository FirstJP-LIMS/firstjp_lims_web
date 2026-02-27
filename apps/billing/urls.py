from django.urls import path
# from . import views
from .views import billing_task, payment_gateway, pricelist, insurance_provider, invoicing, rebate_views

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
    path('pricelists/<uuid:pk>/', pricelist.pricelist_detail_view, name='pricelist_detail'),
    path('pricelists/<uuid:pk>/edit/', pricelist.pricelist_update_view, name='pricelist_update'),
    path('pricelists/<uuid:pk>/delete/', pricelist.pricelist_delete_view, name='pricelist_delete'),
    path('pricelists/<uuid:pk>/toggle-active/', pricelist.pricelist_toggle_active_view, name='pricelist_toggle_active'), # To be used in details to set active and inactive...

    # Billing Info
    path('billings/', billing_task.billing_list_view, name='billing_list'),

    path('billings/create/<uuid:request_id>/', billing_task.billing_create_view, name='billing_create'),
    
    path('billings/<uuid:pk>/detail/', billing_task.billing_detail_view, name='billing_detail'),
    
    path('billings/<uuid:pk>/edit/', billing_task.billing_update_view, name='billing_update'),
    
    path('billings/<uuid:pk>/recalculate/', billing_task.billing_recalculate_view, name='billing_recalculate'),
    
    path('billings/<uuid:pk>/print/', billing_task.billing_print_view, name='billing_print'),

    path('billings/summary/', billing_task.billing_summary_view, name='billing_summary'),
    
    path('billings/bulk-action/', billing_task.billing_bulk_action_view, name='billing_bulk_action'),
    

    # Payment Actions
    path('billings/<uuid:pk>/authorize/', billing_task.authorize_billing_view, name='authorize_billing'),
    
    path('billings/<uuid:pk>/waive/', billing_task.waive_billing_view, name='waive_billing'),
    
    path('billings/<uuid:pk>/confirm-payment/', billing_task.confirm_payment_view, name='confirm_payment'),
    
    # # Payment Gateway (for future implementation)
    # path('billing/<int:pk>/pay-online/', views.initiate_online_payment, name='pay_online'),
    # path('payment/callback/', views.payment_gateway_callback, name='payment_callback'),

 
    # Payments
    path('billings/<uuid:billing_pk>/payment/', billing_task.PaymentCreateView.as_view(), name='payment_create'),
    

    # Insurance Providers
    path('insurance/', insurance_provider.insurance_list_view, name='insurance_list'),
    path('insurance/create/', insurance_provider.insurance_create_view, name='insurance_create'),
    path('insurance/<uuid:pk>/', insurance_provider.insurance_detail_view, name='insurance_detail'),
    path('insurance/<uuid:pk>/edit/', insurance_provider.insurance_update_view, name='insurance_update'),
    path('insurance/<uuid:pk>/delete/', insurance_provider.insurance_delete_view, name='insurance_delete'),
    path('insurance/<uuid:pk>/toggle-active/', insurance_provider.insurance_toggle_active_view, name='insurance_toggle_active'),
    path('insurance/<uuid:pk>/financial-report/', insurance_provider.insurance_financial_report_view, name='insurance_financial_report'),
    
    # Bulk actions
    path('insurance/bulk-deactivate/', insurance_provider.insurance_bulk_deactivate_view, name='insurance_bulk_deactivate'),


     # INVOICE RENEWED
    path('invoices/', invoicing.invoice_list_view, name='invoice_list'),
    path('invoices/generate/', invoicing.generate_invoice_view, name='generate_invoice'),

    path('invoices/<uuid:pk>/', invoicing.invoice_detail_view, name='invoice_detail'),

    path('invoices/<uuid:pk>/payment/',    invoicing.record_invoice_payment_view, name='invoice_payment'),

    path('invoices/<uuid:pk>/send/', invoicing.send_invoice_view, name='invoice_send'),
    
    path('invoices/<uuid:pk>/cancel/', invoicing.cancel_invoice_view, name='invoice_cancel'),
    
    path('invoices/<uuid:pk>/pdf/', invoicing.download_invoice_pdf_view, name='invoice_pdf'),

    path('invoices/<uuid:pk>/payments/<uuid:payment_pk>/receipt/', invoicing.download_receipt_pdf_view, name='invoice_receipt'),


    # Referrer 
    path('referrer/', rebate_views.referrer_list_view, name='referrer_list'),

    path('referrer/create', rebate_views.referrer_create_view, name='referrer_create'),
    
    path('referrer/<uuid:pk>/edit/', rebate_views.referrer_update_view, name='referrer_update'),
    
    path('referrer/<uuid:pk>/detail/', rebate_views.referrer_detail_view, name='referrer_detail'),

    # path('referrer/<uuid:pk>/statement/', rebate_views.rebate_statement_view, name='referrer_statement'),
    path('referrer/statement/', rebate_views.rebate_statement_view, name='referrer_statement'),

    path('rebate/<uuid:pk>/statement/', rebate_views.settlement_detail_view, name='statement_detail'),

    # Reports
    path('reports/', billing_task.BillingReportView.as_view(), name='reports'),
    
]

 