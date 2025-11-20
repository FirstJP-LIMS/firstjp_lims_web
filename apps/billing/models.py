from django.db import models
from django.conf import settings
from django.utils import timezone
from decimal import Decimal
from django.db.models import Sum


# ==========================================
# 1. PRICE LISTS & TEST PRICING
# ==========================================

class PriceList(models.Model):
    """
    Different price lists for different payment types.
    Example: Cash patients pay more than HMO rates.
    """
    PRICE_LIST_TYPES = [
        ('RETAIL', 'Retail (Cash Patients)'),
        ('HMO', 'HMO/Insurance'),
        ('CORPORATE', 'Corporate Account'),
        ('NHIS', 'NHIS (Government)'),
        ('STAFF', 'Staff Discount'),
    ]
    
    vendor = models.ForeignKey('tenants.Vendor', on_delete=models.CASCADE, related_name='price_lists')
    
    name = models.CharField(max_length=100, help_text="e.g., 'AVON HMO Rates'")
    price_type = models.CharField(max_length=20, choices=PRICE_LIST_TYPES)
    
    # For HMO/Corporate
    client_name = models.CharField(max_length=200, blank=True,  help_text="HMO name or company name")
    contract_number = models.CharField(max_length=100, blank=True)
    
    # Discount
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="Overall discount on retail prices")
    
    # Validity
    effective_date = models.DateField(default=timezone.now)
    expiry_date = models.DateField(null=True, blank=True)
    
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('vendor', 'name')
        ordering = ['price_type', 'name']
    
    def __str__(self):
        return f"{self.name} ({self.get_price_type_display()})"


class TestPrice(models.Model):
    """
    Specific price for a test in a price list.
    """
    price_list = models.ForeignKey(PriceList, on_delete=models.CASCADE, related_name='test_prices')
    test = models.ForeignKey('labs.VendorTest', on_delete=models.CASCADE, related_name='prices')
    
    price = models.DecimalField(max_digits=10, decimal_places=2, help_text="Price for this test in this price list")
    
    # Optional: Cost tracking
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Lab's cost to perform this test")
    
    class Meta:
        unique_together = ('price_list', 'test')
    
    def profit_margin(self):
        """Calculate profit margin percentage"""
        if self.cost_price and self.cost_price > 0:
            return ((self.price - self.cost_price) / self.price) * 100
        return None
    
    def __str__(self):
        return f"{self.test.code} - ₦{self.price} ({self.price_list.name})"


# ==========================================
# 2. INSURANCE/HMO PROVIDERS
# ==========================================

class InsuranceProvider(models.Model):
    """
    HMO/Insurance companies that labs work with.
    """
    vendor = models.ForeignKey('tenants.Vendor', on_delete=models.CASCADE, related_name='insurance_providers')
    
    name = models.CharField(max_length=200, help_text="e.g., AVON HMO, Hygeia HMO")
    code = models.CharField(max_length=20, unique=True, help_text="Short code: AVON, HYG")
    
    contact_person = models.CharField(max_length=200, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    
    # Payment Terms
    payment_terms_days = models.IntegerField(default=30, help_text="Days until payment due")
    credit_limit = models.DecimalField(max_digits=12, decimal_places=2, default=0, help_text="Maximum outstanding balance allowed")
    
    # Status
    is_active = models.BooleanField(default=True)
    requires_preauth = models.BooleanField(default=False, 
                                           help_text="Require pre-authorization for tests")
    
    # Linked price list
    price_list = models.ForeignKey(PriceList, on_delete=models.SET_NULL, null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['name']
    
    def get_outstanding_balance(self):
        """Calculate total unpaid invoices"""
        return self.invoices.filter(
            status__in=['SENT', 'OVERDUE']
        ).aggregate(
            total=Sum('total_amount')
        )['total'] or Decimal('0.00')
    
    def is_over_credit_limit(self):
        """Check if outstanding balance exceeds credit limit"""
        return self.get_outstanding_balance() > self.credit_limit
    
    def __str__(self):
        return f"{self.name} ({self.code})"


# ==========================================
# 3. CORPORATE ACCOUNTS
# ==========================================

class CorporateClient(models.Model):
    """
    Companies with monthly billing accounts.
    """
    vendor = models.ForeignKey('tenants.Vendor', on_delete=models.CASCADE, related_name='corporate_clients')
    
    company_name = models.CharField(max_length=200)
    account_number = models.CharField(max_length=50, unique=True)
    
    # Contact Details
    contact_person = models.CharField(max_length=200)
    phone = models.CharField(max_length=20)
    email = models.EmailField()
    billing_address = models.TextField()
    
    # Financial Terms
    payment_terms_days = models.IntegerField(default=60, help_text="Days until payment due")
    credit_limit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Linked price list
    price_list = models.ForeignKey(PriceList, on_delete=models.SET_NULL, null=True, blank=True)
    
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['company_name']
    
    def get_outstanding_balance(self):
        """Calculate total unpaid invoices"""
        return self.invoices.filter(
            status__in=['SENT', 'OVERDUE']
        ).aggregate(
            total=Sum('total_amount')
        )['total'] or Decimal('0.00')
    
    def __str__(self):
        return f"{self.company_name} ({self.account_number})"


# ==========================================
# 4. ENHANCED BILLING INFORMATION
# ==========================================

class BillingInformation(models.Model):
    """
    Enhanced version of your existing BillingInformation model.
    Links TestRequest to payment details.
    """
    vendor = models.ForeignKey('tenants.Vendor', on_delete=models.CASCADE, related_name='billing_records')
    request = models.OneToOneField('labs.TestRequest', on_delete=models.CASCADE, related_name='billing_info')
    
    BILLING_TYPES = [
        ('CASH', 'Cash/Self-Pay'),
        ('HMO', 'HMO/Insurance'),
        ('CORPORATE', 'Corporate Account'),
        ('NHIS', 'NHIS (Government)'),
        ('STAFF', 'Staff (Internal)'),
    ]
    billing_type = models.CharField(max_length=20, choices=BILLING_TYPES, default='CASH')
    
    # Price List Applied
    price_list = models.ForeignKey(PriceList, on_delete=models.SET_NULL, null=True, blank=True, help_text="Which price list was used")
    
    # For HMO patients
    insurance_provider = models.ForeignKey(InsuranceProvider, on_delete=models.SET_NULL, null=True, blank=True)
    policy_number = models.CharField(max_length=100, blank=True)
    pre_authorization_code = models.CharField(max_length=100, blank=True, help_text="HMO authorization number")
    
    # For Corporate patients
    corporate_client = models.ForeignKey(CorporateClient, on_delete=models.SET_NULL, null=True, blank=True)
    employee_id = models.CharField(max_length=100, blank=True)
    
    # Amounts
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Patient Portion (for HMO with co-pay)
    patient_portion = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Amount patient must pay (co-pay)")
    insurance_portion = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Amount HMO will pay")
    
    # Payment Status
    PAYMENT_STATUS = [
        ('UNPAID', 'Unpaid'),
        ('PARTIAL', 'Partially Paid'),
        ('PAID', 'Fully Paid'),
        ('INVOICED', 'Invoiced (Awaiting Payment)'),
        ('OVERDUE', 'Overdue'),
        ('WAIVED', 'Waived/Written Off'),
    ]
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default='UNPAID')
    
    # Notes
    billing_notes = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['vendor', 'billing_type']),
            models.Index(fields=['payment_status']),
        ]
    
    def calculate_totals(self):
        """Auto-calculate billing amounts"""
        # Get all test assignments for this request
        assignments = self.request.test_assignments.all()
        
        subtotal = Decimal('0.00')
        for assignment in assignments:
            # Get price based on price list
            if self.price_list:
                try:
                    test_price = TestPrice.objects.get(
                        price_list=self.price_list,
                        test=assignment.test
                    )
                    subtotal += test_price.price
                except TestPrice.DoesNotExist:
                    # Fallback to test's default price
                    subtotal += assignment.test.price
            else:
                subtotal += assignment.test.price
        
        self.subtotal = subtotal
        self.total_amount = subtotal - self.discount + self.tax
        
        # Calculate patient vs insurance portions
        if self.billing_type == 'HMO' and self.insurance_provider:
            # Example: Patient pays 10%, HMO pays 90%
            copay_percentage = Decimal('0.10')  # This could come from InsuranceProvider
            self.patient_portion = self.total_amount * copay_percentage
            self.insurance_portion = self.total_amount - self.patient_portion
        else:
            self.patient_portion = self.total_amount
            self.insurance_portion = Decimal('0.00')
        
        self.save()
    
    def __str__(self):
        return f"Billing for {self.request.request_id} - ₦{self.total_amount}"


# ==========================================
# 5. PAYMENT TRANSACTIONS
# ==========================================

class Payment(models.Model):
    """
    Individual payment transactions.
    One billing can have multiple payments (installments).
    """
    PAYMENT_METHODS = [
        ('CASH', 'Cash'),
        ('POS', 'POS (Card)'),
        ('TRANSFER', 'Bank Transfer'),
        ('CHEQUE', 'Cheque'),
        ('MOBILE', 'Mobile Money'),
    ]
    
    billing = models.ForeignKey(BillingInformation, on_delete=models.CASCADE, related_name='payments')
    
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS)
    
    # Transaction Details
    transaction_reference = models.CharField(max_length=100, blank=True,
                                             help_text="POS ref, transfer ref, etc.")
    payment_date = models.DateTimeField(default=timezone.now)
    
    # Who collected payment
    collected_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    
    notes = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-payment_date']
    
    def save(self, *args, **kwargs):
        """Update billing payment status when payment is made"""
        super().save(*args, **kwargs)
        
        # Calculate total payments
        total_paid = self.billing.payments.aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0.00')
        
        # Update billing status
        if total_paid >= self.billing.total_amount:
            self.billing.payment_status = 'PAID'
        elif total_paid > 0:
            self.billing.payment_status = 'PARTIAL'
        else:
            self.billing.payment_status = 'UNPAID'
        
        self.billing.save(update_fields=['payment_status'])
    
    def __str__(self):
        return f"₦{self.amount} - {self.get_payment_method_display()} - {self.payment_date.date()}"


# ==========================================
# 6. INVOICES (For HMO & Corporate)
# ==========================================

class Invoice(models.Model):
    """
    Monthly invoices sent to HMOs/Corporate clients.
    Groups multiple billing records into one invoice.
    """
    INVOICE_STATUS = [
        ('DRAFT', 'Draft'),
        ('SENT', 'Sent'),
        ('PARTIAL', 'Partially Paid'),
        ('PAID', 'Paid'),
        ('OVERDUE', 'Overdue'),
        ('CANCELLED', 'Cancelled'),
    ]
    
    vendor = models.ForeignKey('tenants.Vendor', on_delete=models.CASCADE, related_name='invoices')
    
    # Invoice Details
    invoice_number = models.CharField(max_length=50, unique=True)
    invoice_date = models.DateField(default=timezone.now)
    due_date = models.DateField()
    
    # Client (either HMO or Corporate)
    insurance_provider = models.ForeignKey(InsuranceProvider, on_delete=models.SET_NULL, 
                                           null=True, blank=True, related_name='invoices')
    corporate_client = models.ForeignKey(CorporateClient, on_delete=models.SET_NULL, 
                                         null=True, blank=True, related_name='invoices')
    
    # Period covered
    period_start = models.DateField()
    period_end = models.DateField()
    
    # Amounts
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    status = models.CharField(max_length=20, choices=INVOICE_STATUS, default='DRAFT')
    
    # Linked billing records
    billing_records = models.ManyToManyField(BillingInformation, related_name='invoices')
    
    # Notes
    notes = models.TextField(blank=True)
    
    # Tracking
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-invoice_date']
        indexes = [
            models.Index(fields=['vendor', 'status']),
            models.Index(fields=['due_date']),
        ]
    
    def calculate_totals(self):
        """Calculate invoice totals from linked billing records"""
        subtotal = self.billing_records.filter(
            billing_type__in=['HMO', 'CORPORATE']
        ).aggregate(
            total=Sum('insurance_portion')
        )['total'] or Decimal('0.00')
        
        self.subtotal = subtotal
        self.total_amount = subtotal + self.tax
        self.save()
    
    def balance_due(self):
        """Calculate remaining balance"""
        return self.total_amount - self.amount_paid
    
    def is_overdue(self):
        """Check if invoice is past due date"""
        return timezone.now().date() > self.due_date and self.status not in ['PAID', 'CANCELLED']
    
    def __str__(self):
        client = self.insurance_provider or self.corporate_client
        return f"INV-{self.invoice_number} - {client} - ₦{self.total_amount}"


# ==========================================
# 7. INVOICE PAYMENTS
# ==========================================

class InvoicePayment(models.Model):
    """
    Payments received against invoices from HMOs/Corporate clients.
    """
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='payments')
    
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_date = models.DateField(default=timezone.now)
    
    PAYMENT_METHODS = [
        ('TRANSFER', 'Bank Transfer'),
        ('CHEQUE', 'Cheque'),
        ('CASH', 'Cash'),
    ]
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS)
    reference_number = models.CharField(max_length=100, blank=True)
    
    notes = models.TextField(blank=True)
    
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    recorded_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-payment_date']
    
    def save(self, *args, **kwargs):
        """Update invoice payment status"""
        super().save(*args, **kwargs)
        
        # Calculate total payments
        total_paid = self.invoice.payments.aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0.00')
        
        self.invoice.amount_paid = total_paid
        
        # Update status
        if total_paid >= self.invoice.total_amount:
            self.invoice.status = 'PAID'
        elif total_paid > 0:
            self.invoice.status = 'PARTIAL'
        
        self.invoice.save()
    
    def __str__(self):
        return f"₦{self.amount} - {self.invoice.invoice_number} - {self.payment_date}"