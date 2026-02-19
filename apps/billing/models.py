
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import logging

from django.conf import settings
from django.db import models
from django.db.models import Sum
from django.utils import timezone
import uuid


logger = logging.getLogger(__name__)


# ------------------------
# Helper for safe Decimal
# ------------------------
def D(value):
    """Return Decimal from value safely and quantize to 2 decimal places."""
    try:
        d = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        d = Decimal('0.00')
    # Quantize to 2 decimal places for currency
    return d.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


# ==========================================
# 1. PRICE LISTS & TEST PRICING
# ==========================================

class PriceList(models.Model):
    PRICE_LIST_TYPES = [
        ('RETAIL', 'Retail (Cash Patients)'),
        ('HMO', 'HMO/Insurance'),
        ('CORPORATE', 'Corporate Account'),
        ('NHIS', 'NHIS (Government)'),
        ('STAFF', 'Staff Discount'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    vendor = models.ForeignKey('tenants.Vendor', on_delete=models.CASCADE, related_name='price_lists')
    name = models.CharField(max_length=100, help_text="e.g., 'AVON HMO Rates'")
    price_type = models.CharField(max_length=20, choices=PRICE_LIST_TYPES)

    client_name = models.CharField(max_length=200, blank=True, help_text="HMO name or company name")
    contract_number = models.CharField(max_length=100, blank=True)

    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="Overall discount on retail prices")

    tax_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="Tax % applied AFTER discounts (e.g., 7.5%)")
    
    max_discount_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, help_text="Maximum discount allowed (e.g., ₦2000 max off)")
    
    allow_overrides = models.BooleanField(default=False, help_text="Permit staff to override discount rules")

    effective_date = models.DateField(default=timezone.now)
    expiry_date = models.DateField(null=True, blank=True)
    
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('vendor', 'name')
        ordering = ['price_type', 'name']
    
    @property
    def status(self):
        if not self.is_active:
            return "Inactive"
        if self.expiry_date:
            return "Expired"
        return "Active"

    # slug 
    def __str__(self):
        return f"{self.name} ({self.get_price_type_display()})"


class TestPrice(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    price_list = models.ForeignKey(PriceList, on_delete=models.CASCADE, related_name='test_prices')
    test = models.ForeignKey('labs.VendorTest', on_delete=models.CASCADE, related_name='prices')
    price = models.DecimalField(max_digits=12, decimal_places=2, help_text="Price for this test in this price list")

    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0,help_text="Percentage discount for this specific test")

    cost_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True,help_text="Lab's cost to perform this test")

    class Meta:
        unique_together = ('price_list', 'test')

    def profit_margin(self):
        """Calculate profit margin percentage safely."""
        try:
            if self.cost_price and D(self.cost_price) > D(0):
                margin = (D(self.price) - D(self.cost_price)) / D(self.price) * D(100)
                return margin.quantize(Decimal('0.01'))
        except Exception:
            return None
        return None

    def __str__(self):
        return f"{self.test.code} - ₦{self.price} ({self.price_list.name})"

# ==========================================
# 2. INSURANCE/HMO PROVIDERS
# ==========================================

class InsuranceProvider(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vendor = models.ForeignKey('tenants.Vendor', on_delete=models.CASCADE, related_name='insurance_providers')

    name = models.CharField(max_length=200, help_text="e.g., AVON HMO, Hygeia HMO")
    code = models.CharField(max_length=20, help_text="Short code: AVON, HYG")

    contact_person = models.CharField(max_length=200, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)

    payment_terms_days = models.IntegerField(default=30, help_text="Days until payment due")
    credit_limit = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    patient_copay_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        default=Decimal('0.60'),
        help_text="Patient co-pay percentage (0.60 = 60%)"
    )

    is_active = models.BooleanField(default=True)
    requires_preauth = models.BooleanField(default=False, help_text="Require pre-authorization for tests")

    price_list = models.ForeignKey(PriceList, on_delete=models.SET_NULL, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        unique_together = [['vendor', 'code']]

    def get_outstanding_balance(self):
        """
        Calculates how much the HMO specifically owes the lab.
        Excludes the patient portion entirely.
        """
        stats = self.billing_records.filter(
            payment_status__in=['UNPAID', 'PARTIAL', 'AUTHORIZED', 'INVOICED', 'OVERDUE']
        ).aggregate(
            total_owed=Sum('insurance_portion'),
            total_paid=Sum('insurance_amount_paid')
        )
        
        owed = stats['total_owed'] or Decimal('0.00')
        paid = stats['total_paid'] or Decimal('0.00')
        
        return (owed - paid).quantize(Decimal('0.01'))

    def is_over_credit_limit(self):
        """
        Checks if the HMO's debt exceeds the trust limit set by the lab.
        """
        if self.credit_limit <= 0:
            return False  # 0 means unlimited credit
        return self.get_outstanding_balance() > Decimal(self.credit_limit)

    def get_utilization_percentage(self):
        """
        Useful for the UI: Shows how much of the credit limit is used.
        """
        if self.credit_limit <= 0:
            return 0
        balance = self.get_outstanding_balance()
        return (balance / Decimal(self.credit_limit)) * 100

    def is_over_credit_limit(self):
        return self.get_outstanding_balance() > D(self.credit_limit)

    def __str__(self):
        return f"{self.name} ({self.code})"

# ==========================================
# 3. CORPORATE ACCOUNTS
# ==========================================

class CorporateClient(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vendor = models.ForeignKey('tenants.Vendor', on_delete=models.CASCADE, related_name='corporate_clients')

    company_name = models.CharField(max_length=200)
    bank_name = models.CharField(max_length=100, blank=True, help_text="Bank name")
    bank_account_number = models.CharField(max_length=50, blank=True, help_text="Internal account number")

    contact_person = models.CharField(max_length=200)
    phone = models.CharField(max_length=20)
    email = models.EmailField()
    billing_address = models.TextField()

    payment_terms_days = models.IntegerField(default=60, help_text="Days until payment due")
    credit_limit = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    special_discount_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="Extra discount for corporate clients")

    max_discount_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, help_text="Corporate discount cap")

    price_list = models.ForeignKey(PriceList, on_delete=models.SET_NULL, null=True, blank=True)

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['company_name']
        unique_together = [['vendor', 'bank_account_number']]

    def get_outstanding_balance(self):
        total = self.invoices.filter(status__in=['SENT', 'OVERDUE']).aggregate(total=Sum('total_amount'))['total']
        return D(total or Decimal('0.00'))

    def __str__(self):
        return f"{self.company_name} on payment terms {self.payment_terms_days} days"

# ==========================================
# 4. BILLING INFORMATION (fixed)
# ==========================================

class BillingInformation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
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

    price_list = models.ForeignKey('billing.PriceList', on_delete=models.SET_NULL, null=True, blank=True, help_text="Which price list was applied")

    insurance_provider = models.ForeignKey('billing.InsuranceProvider', on_delete=models.SET_NULL, null=True, blank=True, related_name="billing_records")

    policy_number = models.CharField(max_length=100, blank=True)
    pre_authorization_code = models.CharField(max_length=100, blank=True)

    corporate_client = models.ForeignKey(CorporateClient, on_delete=models.SET_NULL, null=True, blank=True)
    employee_id = models.CharField(max_length=100, blank=True)

    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    manual_discount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    waiver_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    tax = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))

    patient_portion = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    insurance_portion = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))

    patient_amount_paid = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))

    insurance_amount_paid = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    
    PAYMENT_STATUS = [
        ('UNPAID', 'Unpaid'),
        ('PARTIAL', 'Partially Paid'),
        ('AUTHORIZED', 'Authorized to Proceed'),
        ('PAID', 'Fully Paid'),
        ('INVOICED', 'Invoiced (Awaiting Payment)'),
        ('OVERDUE', 'Overdue'),
        ('WAIVED', 'Waived/Written Off'),
    ]
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default='UNPAID')

    billing_notes = models.TextField(blank=True)

    # Waive payment 
    authorized_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='billing_authorizations'
    )
    authorized_at = models.DateTimeField(null=True, blank=True)
    authorization_reason = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['vendor', 'billing_type']),
            models.Index(fields=['payment_status']),
        ]

    # -----------------------------
    # Calculation engine
    # -----------------------------
    def _calculate_totals_internal(self):
        """
        Finalized Calculation Engine:
        1. Aggregates retail price from requested tests.
        2. Applies PriceList, Corporate, and Manual discounts.
        3. Calculates Tax on the discounted amount.
        4. Splits the Final Total into Patient vs Insurance portions.
        """
        try:
            tests = self.request.requested_tests.all()
        except AttributeError:
            tests = []

        if not tests:
            # Zero out everything if no tests exist
            for field in ['subtotal', 'discount', 'tax', 'total_amount', 'patient_portion', 'insurance_portion']:
                setattr(self, field, D('0.00'))
            return

        running_subtotal = D('0.00')
        running_test_discount = D('0.00')

        # 1. Price Collection
        for lab_test in tests:
            price = D('0.00')
            if self.price_list:
                price_func = getattr(lab_test, 'get_price_from_price_list', None)
                price = D(price_func(self.price_list)) if callable(price_func) else D(getattr(lab_test, 'price', 0))
                
                # Test-specific discount from PriceList
                try:
                    test_price_obj = lab_test.prices.get(price_list=self.price_list)
                    running_test_discount += price * (D(test_price_obj.discount_percentage) / D(100))
                except Exception:
                    pass
            else:
                price = D(getattr(lab_test, 'price', 0))

            running_subtotal += price

        # 2. Global Discount Logic
        price_list_discount = D('0.00')
        if self.price_list and self.price_list.discount_percentage:
            price_list_discount = running_subtotal * (D(self.price_list.discount_percentage) / D(100))
            if self.price_list.max_discount_amount:
                price_list_discount = min(price_list_discount, D(self.price_list.max_discount_amount))

        corporate_discount = D('0.00')
        if self.corporate_client and self.corporate_client.special_discount_percentage:
            corporate_discount = running_subtotal * (D(self.corporate_client.special_discount_percentage) / D(100))

        # Sum all discounts
        manual_adj = D(self.manual_discount or 0) + D(self.waiver_amount or 0)
        self.discount = min(running_test_discount + price_list_discount + corporate_discount + manual_adj, running_subtotal)

        # 3. Tax and Final Amount
        taxable_amount = running_subtotal - self.discount
        self.tax = D('0.00')
        if self.price_list and self.price_list.tax_percentage:
            self.tax = (taxable_amount * (D(self.price_list.tax_percentage) / D(100))).quantize(D('0.01'))

        self.subtotal = running_subtotal
        self.total_amount = taxable_amount + self.tax

        # 4. Portion Split (The "Who Pays What" Logic)
        if self.billing_type in ['HMO', 'NHIS'] and self.insurance_provider:
            # patient_copay_percentage (e.g., 0.60 for 60%)
            patient_rate = D(getattr(self.insurance_provider, "patient_copay_percentage", 0))
            
            # Don't overwrite if insurance has already paid (prevents recalculating locked history)
            if self.insurance_amount_paid <= 0:
                self.patient_portion = (self.total_amount * patient_rate).quantize(D('0.01'))
                self.insurance_portion = self.total_amount - self.patient_portion
        elif self.billing_type == 'CORPORATE':
            self.insurance_portion = self.total_amount
            self.patient_portion = D('0.00')
        else:
            self.patient_portion = self.total_amount
            self.insurance_portion = D('0.00')

    def save(self, *args, **kwargs):
        """
        Recalculate totals before save. Use a compact update_fields list to avoid missing important fields.
        """

        # Always recalc before saving
        self._calculate_totals_internal()

        # Build update_fields for existing records to avoid accidental omission
        if not self.pk:
            # New -> full save
            super().save(*args, **kwargs)
        else:
            update_fields = [
                'subtotal', 'discount', 'manual_discount', 'waiver_amount',
                'tax', 'total_amount', 'patient_portion', 'insurance_portion',
                'patient_amount_paid', 'insurance_amount_paid',   # ← ADD THESE
                'payment_status', 'price_list', 'billing_type',
                'billing_notes', 'corporate_client', 'insurance_provider', 'updated_at'
            ]
            # remove duplicates and non-existent attributes just in case
            update_fields = [f for f in dict.fromkeys(update_fields) if hasattr(self, f)]
            super().save(update_fields=update_fields)

    @property
    def is_payment_cleared(self):
        if self.payment_status in ['PAID', 'AUTHORIZED', 'WAIVED']:
            return True
        if self.billing_type == 'HMO':
            return self.patient_amount_paid >= self.patient_portion
        if self.billing_type == 'CORPORATE':
            # Corporate: clear to proceed once billing is set up (company pays later via invoice)
            return True
        return False

    def update_payment_status(self):
        """
        Call this whenever a payment is made.
        """
        total_paid = self.patient_amount_paid + self.insurance_amount_paid
        
        if total_paid >= self.total_amount:
            self.payment_status = 'PAID'
        elif self.insurance_amount_paid > 0:
            # If the insurer has started paying, it's definitely in voiced/partial
            self.payment_status = 'PARTIAL'
        elif self.patient_amount_paid >= self.patient_portion and self.insurance_portion > 0:
            # Patient paid their percentage, but HMO discount is still standing.
            # We set it to PARTIAL or keep it INVOICED so the HMO logic sees it
            self.payment_status = 'PARTIAL' 
        elif self.patient_amount_paid > 0:
            self.payment_status = 'PARTIAL'
        
        self.save(update_fields=['payment_status'])

    def get_balance_due(self):
        total_paid = self.payments.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        return Decimal(self.total_amount) - Decimal(total_paid)

    def is_fully_paid(self):
        # Logic: Total must be > 0 and balance must be <= 0
        # OR the status must be explicitly PAID or WAIVED
        if self.payment_status in ['PAID', 'WAIVED']:
            return True
        
        balance = self.get_balance_due()
        if self.total_amount > 0:
            return balance <= 0
        return False

    def __str__(self):
        return f"Billing for {getattr(self.request, 'request_id', str(self.pk))} - ₦{self.total_amount}"


# ==========================================
# 6. INVOICES (For HMO & Corporate)
# ==========================================

class Invoice(models.Model):
    INVOICE_STATUS = [
        ('DRAFT', 'Draft'),
        ('SENT', 'Sent'),
        ('PARTIAL', 'Partially Paid'),
        ('PAID', 'Paid'),
        ('OVERDUE', 'Overdue'),
        ('CANCELLED', 'Cancelled'),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    vendor = models.ForeignKey('tenants.Vendor', on_delete=models.CASCADE, related_name='invoices')

    invoice_number = models.CharField(max_length=50, unique=True)
    invoice_date = models.DateField(default=timezone.now)
    due_date = models.DateField()

    insurance_provider = models.ForeignKey(InsuranceProvider, on_delete=models.SET_NULL,null=True, blank=True, related_name='invoices')
    corporate_client = models.ForeignKey(CorporateClient, on_delete=models.SET_NULL, null=True, blank=True, related_name='invoices')

    period_start = models.DateField()
    period_end = models.DateField()

    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    tax = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    amount_paid = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))

    status = models.CharField(max_length=20, choices=INVOICE_STATUS, default='DRAFT')

    billing_records = models.ManyToManyField(BillingInformation, related_name='invoices')

    notes = models.TextField(blank=True)

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
        """
        Unified calculation: Sums the appropriate portions based on client type.
        """
        records = self.billing_records.all()
        
        if self.insurance_provider:
            # For HMOs, we only bill the insurance_portion (after patient copay)
            total = records.aggregate(Sum('insurance_portion'))['insurance_portion__sum']
        else:
            # For Corporate, we usually bill the total_amount (100% coverage)
            total = records.aggregate(Sum('total_amount'))['total_amount__sum']
            
        self.total_amount = Decimal(total or 0).quantize(Decimal('0.01'))
        self.save(update_fields=['total_amount', 'updated_at'])

    def add_billing_records(self, record_ids):
        """
        Adds records for either HMO or Corporate and updates their status.
        """
        # Dynamic filter based on whether this is an HMO or Corporate Invoice
        filter_kwargs = {'id__in': record_ids, 'payment_status__in': ['UNPAID', 'PARTIAL', 'AUTHORIZED']}
        
        if self.insurance_provider:
            filter_kwargs['insurance_provider'] = self.insurance_provider
        elif self.corporate_client:
            filter_kwargs['corporate_client'] = self.corporate_client

        eligible_records = BillingInformation.objects.filter(**filter_kwargs)
        
        if eligible_records.exists():
            self.billing_records.add(*eligible_records)
            # Mark as INVOICED to hide them from the 'Ready to Bill' list
            eligible_records.update(payment_status='INVOICED')
            self.calculate_totals()
            
    def balance_due(self):
        return D(self.total_amount) - D(self.amount_paid)

    def is_overdue(self):
        return timezone.now().date() > self.due_date and self.status not in ['PAID', 'CANCELLED']

    def __str__(self):
        client = self.insurance_provider or self.corporate_client
        return f"INV-{self.invoice_number} - {client} - ₦{self.total_amount}"


# ==========================================
# 5. PAYMENT TRANSACTIONS
# ==========================================

class Payment(models.Model):
    PAYMENT_METHODS = [
        ('CASH', 'Cash'),
        ('POS', 'POS (Card)'),
        ('TRANSFER', 'Bank Transfer'),
        ('CHEQUE', 'Cheque'),
        ('MOBILE', 'Mobile Money'),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    billing = models.ForeignKey(BillingInformation, on_delete=models.CASCADE, related_name='payments')

    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS)

    transaction_reference = models.CharField(max_length=100, blank=True,
    help_text="POS ref, transfer ref, etc.")
    payment_date = models.DateTimeField(default=timezone.now)

    collected_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-payment_date']

    # Inside Payment model save()
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        
        total_paid = self.billing.payments.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        total_amt = Decimal(self.billing.total_amount)

        # Only mark as PAID if there was actually something to pay
        if total_amt > 0 and Decimal(total_paid) >= total_amt:
            self.billing.payment_status = 'PAID'
        elif Decimal(total_paid) > 0:
            self.billing.payment_status = 'PARTIAL'
        else:
            # If it was AUTHORIZED or WAIVED, don't overwrite it back to UNPAID 
            # unless total_paid is literally 0 and it wasn't authorized.
            if self.billing.payment_status not in ['AUTHORIZED', 'WAIVED']:
                self.billing.payment_status = 'UNPAID'

        self.billing.save(update_fields=['payment_status', 'updated_at'])

    def __str__(self):
        return f"₦{self.amount} - {self.get_payment_method_display()} - {self.payment_date.date()}"


# ==========================================
# 7. INVOICE PAYMENTS
# ==========================================

class InvoicePayment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='payments')

    amount = models.DecimalField(max_digits=14, decimal_places=2)
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
        super().save(*args, **kwargs)

        total_paid = self.invoice.payments.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        self.invoice.amount_paid = D(total_paid)

        # Update status
        if D(total_paid) >= D(self.invoice.total_amount):
            self.invoice.status = 'PAID'
        elif D(total_paid) > D('0.00'):
            self.invoice.status = 'PARTIAL'

        self.invoice.save(update_fields=['amount_paid', 'status', 'updated_at'])

    def __str__(self):
        return f"₦{self.amount} - {self.invoice.invoice_number} - {self.payment_date}"


# class Payment(models.Model):
#     """
#     Records individual payment transactions for billing records.
#     Supports multiple payment methods and partial payments.
#     """
    
#     vendor = models.ForeignKey(
#         'tenants.Vendor',
#         on_delete=models.CASCADE,
#         related_name='payments'
#     )
    
#     billing = models.ForeignKey(
#         'billing.BillingInformation',
#         on_delete=models.CASCADE,
#         related_name='payments'
#     )
    
#     # Payment Details
#     amount = models.DecimalField(
#         max_digits=12,
#         decimal_places=2,
#         help_text="Amount paid in this transaction"
#     )
    
#     PAYMENT_METHODS = [
#         ('cash', 'Cash'),
#         ('bank_transfer', 'Bank Transfer'),
#         ('pos', 'POS/Card Payment'),
#         ('cheque', 'Cheque'),
#         ('mobile_money', 'Mobile Money (e.g., PayStack, Flutterwave)'),
#         ('online', 'Online Payment Gateway'),
#         ('insurance_claim', 'Insurance Claim Settlement'),
#         ('corporate_invoice', 'Corporate Invoice Payment'),
#     ]
#     payment_method = models.CharField(
#         max_length=30,
#         choices=PAYMENT_METHODS,
#         default='cash'
#     )
    
#     # Transaction tracking
#     transaction_reference = models.CharField(
#         max_length=200,
#         blank=True,
#         help_text="Bank reference, POS receipt number, or payment gateway transaction ID"
#     )
    
#     receipt_number = models.CharField(
#         max_length=100,
#         unique=True,
#         editable=False,
#         help_text="Internal receipt number generated by system"
#     )
    
#     # For cheques
#     cheque_number = models.CharField(max_length=50, blank=True)
#     cheque_bank = models.CharField(max_length=100, blank=True)
#     cheque_date = models.DateField(null=True, blank=True)
    
#     # Status tracking
#     PAYMENT_STATUS = [
#         ('pending', 'Pending Verification'),
#         ('completed', 'Completed'),
#         ('failed', 'Failed'),
#         ('reversed', 'Reversed/Refunded'),
#         ('cheque_bounced', 'Cheque Bounced'),
#     ]
#     status = models.CharField(
#         max_length=20,
#         choices=PAYMENT_STATUS,
#         default='completed'
#     )
    
#     # Staff tracking
#     received_by = models.ForeignKey(
#         settings.AUTH_USER_MODEL,
#         on_delete=models.SET_NULL,
#         null=True,
#         related_name='payments_received',
#         help_text="Staff member who received/confirmed payment"
#     )
    
#     verified_by = models.ForeignKey(
#         settings.AUTH_USER_MODEL,
#         on_delete=models.SET_NULL,
#         null=True,
#         blank=True,
#         related_name='payments_verified',
#         help_text="Staff member who verified payment (for bank transfers)"
#     )
    
#     # Timestamps
#     payment_date = models.DateTimeField(
#         default=timezone.now,
#         help_text="When payment was received"
#     )
    
#     verified_at = models.DateTimeField(
#         null=True,
#         blank=True,
#         help_text="When payment was verified (for online/transfer payments)"
#     )
    
#     created_at = models.DateTimeField(auto_now_add=True)
#     updated_at = models.DateTimeField(auto_now=True)
    
#     # Notes
#     payment_notes = models.TextField(
#         blank=True,
#         help_text="Additional notes about this payment"
#     )
    
#     class Meta:
#         ordering = ['-payment_date']
#         indexes = [
#             models.Index(fields=['vendor', 'payment_date']),
#             models.Index(fields=['billing', 'status']),
#             models.Index(fields=['receipt_number']),
#         ]
    
#     def save(self, *args, **kwargs):
#         """Generate receipt number if not exists"""
#         if not self.receipt_number:
#             # Generate unique receipt number
#             last_payment = Payment.objects.filter(
#                 vendor=self.vendor
#             ).order_by('-id').first()
            
#             if last_payment and last_payment.receipt_number:
#                 try:
#                     last_num = int(last_payment.receipt_number.split('-')[-1])
#                     new_num = last_num + 1
#                 except (ValueError, IndexError):
#                     new_num = 1
#             else:
#                 new_num = 1
            
#             self.receipt_number = f"RCP-{self.vendor.id}-{new_num:08d}"
        
#         super().save(*args, **kwargs)
    
#     def __str__(self):
#         return f"Payment {self.receipt_number} - ₦{self.amount} ({self.get_payment_method_display()})"

