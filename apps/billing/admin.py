from django.contrib import admin
from django.db.models import Sum
from django.utils.html import format_html
from .models import (
    PriceList, TestPrice, InsuranceProvider, CorporateClient,
    BillingInformation, Payment, Invoice, InvoicePayment
)


# ==========================================
# PRICE LIST ADMIN
# ==========================================

class TestPriceInline(admin.TabularInline):
    model = TestPrice
    extra = 1
    fields = ('test', 'price', 'discount_percentage', 'cost_price')
    autocomplete_fields = ['test']


@admin.register(PriceList)
class PriceListAdmin(admin.ModelAdmin):
    list_display = ('name', 'price_type', 'discount_percentage', 'tax_percentage', 'effective_date', 'expiry_date', 'is_active')
    list_filter = ('price_type', 'is_active', 'vendor')
    search_fields = ('name', 'client_name', 'contract_number')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [TestPriceInline]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('vendor', 'name', 'price_type', 'client_name', 'contract_number')
        }),
        ('Pricing Rules', {
            'fields': ('discount_percentage', 'tax_percentage', 'max_discount_amount', 'allow_overrides')
        }),
        ('Validity Period', {
            'fields': ('effective_date', 'expiry_date', 'is_active')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.is_superuser:
            qs = qs.filter(vendor=request.user.vendor)
        return qs


@admin.register(TestPrice)
class TestPriceAdmin(admin.ModelAdmin):
    list_display = ('test', 'price_list', 'price', 'discount_percentage', 'cost_price', 'margin_display')
    list_filter = ('price_list__vendor', 'price_list')
    search_fields = ('test__name', 'test__code', 'price_list__name')
    autocomplete_fields = ['test', 'price_list']
    
    def margin_display(self, obj):
        margin = obj.profit_margin()
        if margin is not None:
            color = 'green' if margin > 20 else 'orange' if margin > 10 else 'red'
            return format_html('<span style="color: {};">{:.2f}%</span>', color, margin)
        return '-'
    margin_display.short_description = 'Profit Margin'


# ==========================================
# INSURANCE PROVIDER ADMIN
# ==========================================

@admin.register(InsuranceProvider)
class InsuranceProviderAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'credit_limit', 'outstanding_balance_display', 
                   'payment_terms_days', 'is_active')
    list_filter = ('is_active', 'requires_preauth', 'vendor')
    search_fields = ('name', 'code', 'contact_person', 'email')
    readonly_fields = ('created_at', 'outstanding_balance_display')
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('vendor', 'name', 'code', 'is_active')
        }),
        ('Contact Details', {
            'fields': ('contact_person', 'phone', 'email', 'address')
        }),
        ('Financial Terms', {
            'fields': ('payment_terms_days', 'credit_limit', 'default_copay_percentage', 
                      'requires_preauth', 'price_list')
        }),
        ('Status', {
            'fields': ('outstanding_balance_display', 'created_at'),
            'classes': ('collapse',)
        }),
    )
    
    def outstanding_balance_display(self, obj):
        balance = obj.get_outstanding_balance()
        is_over = obj.is_over_credit_limit()
        color = 'red' if is_over else 'green'
        return format_html('<span style="color: {}; font-weight: bold;">₦{:,.2f}</span>', 
                          color, balance)
    outstanding_balance_display.short_description = 'Outstanding Balance'
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.is_superuser:
            qs = qs.filter(vendor=request.user.vendor)
        return qs


# ==========================================
# CORPORATE CLIENT ADMIN
# ==========================================

@admin.register(CorporateClient)
class CorporateClientAdmin(admin.ModelAdmin):
    list_display = ('company_name', 'contact_person', 'credit_limit', 
                   'outstanding_balance_display', 'payment_terms_days', 'is_active')
    list_filter = ('is_active', 'vendor')
    search_fields = ('company_name', 'contact_person', 'email', 'bank_account_number')
    readonly_fields = ('created_at', 'updated_at', 'outstanding_balance_display')
    
    fieldsets = (
        ('Company Information', {
            'fields': ('vendor', 'company_name', 'bank_name', 'bank_account_number', 'is_active')
        }),
        ('Contact Details', {
            'fields': ('contact_person', 'phone', 'email', 'billing_address')
        }),
        ('Financial Terms', {
            'fields': ('payment_terms_days', 'credit_limit', 'special_discount_percentage', 
                      'max_discount_amount', 'price_list')
        }),
        ('Status', {
            'fields': ('outstanding_balance_display', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def outstanding_balance_display(self, obj):
        balance = obj.get_outstanding_balance()
        color = 'red' if balance > obj.credit_limit else 'green'
        return format_html('<span style="color: {}; font-weight: bold;">₦{:,.2f}</span>', 
                          color, balance)
    outstanding_balance_display.short_description = 'Outstanding Balance'
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.is_superuser:
            qs = qs.filter(vendor=request.user.vendor)
        return qs


# ==========================================
# BILLING INFORMATION ADMIN
# ==========================================

class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    readonly_fields = ('payment_date', 'collected_by', 'created_at')
    fields = ('amount', 'payment_method', 'transaction_reference', 
             'payment_date', 'collected_by', 'notes')


@admin.register(BillingInformation)
class BillingInformationAdmin(admin.ModelAdmin):
    list_display = ('request_id_display', 'billing_type', 'total_amount', 
                   'payment_status_display', 'created_at')
    list_filter = ('billing_type', 'payment_status', 'vendor', 'created_at')
    search_fields = ('request__request_id', 'policy_number', 'employee_id')
    readonly_fields = ('subtotal', 'discount', 'tax', 'total_amount', 
                      'patient_portion', 'insurance_portion', 'created_at', 'updated_at',
                      'balance_due_display')
    inlines = [PaymentInline]
    
    fieldsets = (
        ('Request Information', {
            'fields': ('vendor', 'request', 'billing_type')
        }),
        ('Pricing', {
            'fields': ('price_list',)
        }),
        ('Insurance Details', {
            'fields': ('insurance_provider', 'policy_number', 'pre_authorization_code'),
            'classes': ('collapse',)
        }),
        ('Corporate Details', {
            'fields': ('corporate_client', 'employee_id'),
            'classes': ('collapse',)
        }),
        ('Financial Summary', {
            'fields': ('subtotal', 'discount', 'manual_discount', 'waiver_amount', 
                      'tax', 'total_amount', 'patient_portion', 'insurance_portion', 
                      'balance_due_display', 'payment_status')
        }),
        ('Notes', {
            'fields': ('billing_notes',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def request_id_display(self, obj):
        return obj.request.request_id if obj.request else 'N/A'
    request_id_display.short_description = 'Request ID'
    
    def payment_status_display(self, obj):
        colors = {
            'PAID': 'green',
            'PARTIAL': 'orange',
            'UNPAID': 'red',
            'INVOICED': 'blue',
            'OVERDUE': 'darkred',
            'WAIVED': 'gray'
        }
        color = colors.get(obj.payment_status, 'black')
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', 
                          color, obj.get_payment_status_display())
    payment_status_display.short_description = 'Payment Status'
    
    def balance_due_display(self, obj):
        balance = obj.get_balance_due()
        color = 'green' if balance == 0 else 'red'
        return format_html('<span style="color: {}; font-weight: bold;">₦{:,.2f}</span>', 
                          color, balance)
    balance_due_display.short_description = 'Balance Due'
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.is_superuser:
            qs = qs.filter(vendor=request.user.vendor)
        return qs


# ==========================================
# PAYMENT ADMIN
# ==========================================

# @admin.register(Payment)
# class PaymentAdmin(admin.ModelAdmin):
#     list_display = ('billing_request_id', 'amount', 'payment_method', 
#                    'payment_date', 'collected_by')
#     list_filter = ('payment_method', 'payment_date', 'billing__vendor')
#     search_fields = ('transaction_reference', 'billing__request__request_id')
#     readonly_fields = ('payment_date', 'created_at')
    
#     fieldsets = (
#         ('Payment Details', {
#             'fields': ('billing', 'amount', 'payment_method', 'transaction_reference', 
#                       'payment_date')
#         }),
#         ('Additional Information', {
#             'fields': ('collected_by', 'notes', 'created_at')
#         }),
#     )
    
#     def billing_request_id(self, obj):
#         return obj.billing.request.request_id if obj.billing.request else 'N/A'
#     billing_request_id.short_description = 'Request ID'
    
#     def get_queryset(self, request):
#         qs = super().get_queryset(request)
#         if not request.user.is_superuser:
#             qs = qs.filter(billing__vendor=request.user.vendor)
#         return qs


# ==========================================
# INVOICE ADMIN
# ==========================================

class InvoicePaymentInline(admin.TabularInline):
    model = InvoicePayment
    extra = 0
    readonly_fields = ('payment_date', 'recorded_by', 'recorded_at')
    fields = ('amount', 'payment_method', 'reference_number', 
             'payment_date', 'recorded_by', 'notes')


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'client_display', 'invoice_date', 
                   'due_date', 'total_amount', 'status_display')
    list_filter = ('status', 'invoice_date', 'vendor')
    search_fields = ('invoice_number', 'insurance_provider__name', 
                    'corporate_client__company_name')
    readonly_fields = ('subtotal', 'tax', 'total_amount', 'amount_paid', 
                      'balance_due_display', 'created_at', 'updated_at')
    filter_horizontal = ('billing_records',)
    inlines = [InvoicePaymentInline]
    
    fieldsets = (
        ('Invoice Information', {
            'fields': ('vendor', 'invoice_number', 'invoice_date', 'due_date', 'status')
        }),
        ('Client Information', {
            'fields': ('insurance_provider', 'corporate_client')
        }),
        ('Billing Period', {
            'fields': ('period_start', 'period_end')
        }),
        ('Financial Details', {
            'fields': ('subtotal', 'tax', 'total_amount', 'amount_paid', 'balance_due_display')
        }),
        ('Billing Records', {
            'fields': ('billing_records',)
        }),
        ('Additional Information', {
            'fields': ('notes', 'created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def client_display(self, obj):
        if obj.insurance_provider:
            return f"{obj.insurance_provider.name} (HMO)"
        elif obj.corporate_client:
            return f"{obj.corporate_client.company_name} (Corporate)"
        return 'N/A'
    client_display.short_description = 'Client'
    
    def status_display(self, obj):
        colors = {
            'PAID': 'green',
            'PARTIAL': 'orange',
            'SENT': 'blue',
            'OVERDUE': 'red',
            'DRAFT': 'gray',
            'CANCELLED': 'darkgray'
        }
        color = colors.get(obj.status, 'black')
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', 
                          color, obj.get_status_display())
    status_display.short_description = 'Status'
    
    def balance_due_display(self, obj):
        balance = obj.balance_due()
        color = 'green' if balance == 0 else 'red'
        return format_html('<span style="color: {}; font-weight: bold;">₦{:,.2f}</span>', 
                          color, balance)
    balance_due_display.short_description = 'Balance Due'
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.is_superuser:
            qs = qs.filter(vendor=request.user.vendor)
        return qs


@admin.register(InvoicePayment)
class InvoicePaymentAdmin(admin.ModelAdmin):
    list_display = ('invoice_number_display', 'amount', 'payment_method', 
                   'payment_date', 'recorded_by')
    list_filter = ('payment_method', 'payment_date')
    search_fields = ('invoice__invoice_number', 'reference_number')
    readonly_fields = ('payment_date', 'recorded_at')
    
    fieldsets = (
        ('Payment Details', {
            'fields': ('invoice', 'amount', 'payment_method', 'reference_number', 
                      'payment_date')
        }),
        ('Additional Information', {
            'fields': ('notes', 'recorded_by', 'recorded_at')
        }),
    )
    
    def invoice_number_display(self, obj):
        return obj.invoice.invoice_number
    invoice_number_display.short_description = 'Invoice Number'
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.is_superuser:
            qs = qs.filter(invoice__vendor=request.user.vendor)
        return qs