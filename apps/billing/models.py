
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import logging

from django.conf import settings
from django.db import models
from django.db.models import Sum
from django.utils import timezone

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
    price_list = models.ForeignKey(PriceList, on_delete=models.CASCADE, related_name='test_prices')
    test = models.ForeignKey('labs.VendorTest', on_delete=models.CASCADE, related_name='prices')
    price = models.DecimalField(max_digits=12, decimal_places=2, help_text="Price for this test in this price list")

    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0,
                                              help_text="Percentage discount for this specific test")

    cost_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True,
                                     help_text="Lab's cost to perform this test")

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
    vendor = models.ForeignKey('tenants.Vendor', on_delete=models.CASCADE, related_name='insurance_providers')

    name = models.CharField(max_length=200, help_text="e.g., AVON HMO, Hygeia HMO")
    code = models.CharField(max_length=20, help_text="Short code: AVON, HYG")

    contact_person = models.CharField(max_length=200, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)

    payment_terms_days = models.IntegerField(default=30, help_text="Days until payment due")
    credit_limit = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    default_copay_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        default=Decimal('0.10'),
        help_text="Patient co-pay percentage (0.10 = 10%)"
    )

    is_active = models.BooleanField(default=True)
    requires_preauth = models.BooleanField(default=False, help_text="Require pre-authorization for tests")

    price_list = models.ForeignKey(PriceList, on_delete=models.SET_NULL, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        unique_together = [['vendor', 'code']]

    def get_outstanding_balance(self):
        total = self.invoices.filter(status__in=['SENT', 'OVERDUE']).aggregate(total=Sum('total_amount'))['total']
        return D(total or Decimal('0.00'))

    def is_over_credit_limit(self):
        return self.get_outstanding_balance() > D(self.credit_limit)

    def __str__(self):
        return f"{self.name} ({self.code})"


# ==========================================
# 3. CORPORATE ACCOUNTS
# ==========================================

class CorporateClient(models.Model):
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

    special_discount_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0,
                                                      help_text="Extra discount for corporate clients")

    max_discount_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True,
                                              help_text="Corporate discount cap")

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

    price_list = models.ForeignKey('billing.PriceList', on_delete=models.SET_NULL, null=True, blank=True,
                                   help_text="Which price list was applied")

    insurance_provider = models.ForeignKey('billing.InsuranceProvider', on_delete=models.SET_NULL,
                                           null=True, blank=True)
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

    PAYMENT_STATUS = [
        ('UNPAID', 'Unpaid'),
        ('PARTIAL', 'Partially Paid'),
        ('PAID', 'Fully Paid'),
        ('INVOICED', 'Invoiced (Awaiting Payment)'),
        ('OVERDUE', 'Overdue'),
        ('WAIVED', 'Waived/Written Off'),
    ]
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default='UNPAID')

    billing_notes = models.TextField(blank=True)

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
        """Calculate subtotal, discounts, tax and breakdowns safely."""
        try:
            assignments = self.request.test_assignments.all()
        except AttributeError:
            logger.warning("BillingInformation.request has no test_assignments")
            assignments = []

        if not getattr(assignments, 'exists', lambda: False)() or len(assignments) == 0:
            self.subtotal = D('0.00')
            self.discount = D('0.00')
            self.tax = D('0.00')
            self.total_amount = D('0.00')
            self.patient_portion = D('0.00')
            self.insurance_portion = D('0.00')
            return

        subtotal = D('0.00')
        total_test_discount = D('0.00')

        for assignment in assignments:
            try:
                # Prefer price from provided price_list, else fallback to test.price
                if self.price_list:
                    # test.get_price_from_price_list may raise; guard it
                    price = getattr(assignment.test, 'get_price_from_price_list', None)
                    if callable(price):
                        price = assignment.test.get_price_from_price_list(self.price_list)
                    else:
                        # fallback to attribute
                        price = getattr(assignment.test, 'price', None)
                else:
                    price = getattr(assignment.test, 'price', None)

                if price is None:
                    continue

                price = D(price)
                subtotal += price

                # Test-level discount if TestPrice exists for this price list
                if self.price_list:
                    try:
                        test_price_obj = assignment.test.prices.get(price_list=self.price_list)
                        test_disc = D(price) * (D(test_price_obj.discount_percentage) / D(100))
                        total_test_discount += test_disc
                    except assignment.test.prices.model.DoesNotExist:
                        # no test-specific discount for this price list
                        pass
                    except Exception:
                        # avoid breaking on unexpected errors
                        logger.debug("Error fetching test-specific price/discount", exc_info=True)

            except Exception:
                # Do not crash billing due to single assignment error
                logger.exception("Error processing assignment for billing calculation")
                continue

        # PriceList-level discount
        price_list_discount = D('0.00')
        if self.price_list and self.price_list.discount_percentage:
            rate = D(self.price_list.discount_percentage) / D(100)
            price_list_discount = subtotal * rate
            if self.price_list.max_discount_amount:
                price_list_discount = min(price_list_discount, D(self.price_list.max_discount_amount))

        # Corporate discount
        corporate_discount = D('0.00')
        if self.corporate_client and self.corporate_client.special_discount_percentage:
            rate = D(self.corporate_client.special_discount_percentage) / D(100)
            corporate_discount = subtotal * rate
            if self.corporate_client.max_discount_amount:
                corporate_discount = min(corporate_discount, D(self.corporate_client.max_discount_amount))

        override_discount = D(self.manual_discount or Decimal('0.00'))
        waiver_discount = D(self.waiver_amount or Decimal('0.00'))

        total_discount = total_test_discount + price_list_discount + corporate_discount + override_discount + waiver_discount
        # Ensure discount does not exceed subtotal
        if total_discount > subtotal:
            total_discount = subtotal

        self.discount = total_discount

        # Tax calculation: price list tax applies to taxable amount after discounts
        taxable_amount = subtotal - total_discount
        tax_amount = D('0.00')
        if self.price_list and self.price_list.tax_percentage:
            tax_rate = D(self.price_list.tax_percentage) / D(100)
            tax_amount = taxable_amount * tax_rate

        self.tax = tax_amount

        self.subtotal = subtotal
        self.total_amount = taxable_amount + tax_amount

        # Patient vs insurance portions
        if self.billing_type == 'HMO' and self.insurance_provider:
            copay = D(getattr(self.insurance_provider, "default_copay_percentage", Decimal('0.10')))
            # Ensure copay is <= 1
            if copay > D(1):
                copay = D('1.00')
            self.patient_portion = (self.total_amount * copay).quantize(Decimal('0.01'))
            self.insurance_portion = (self.total_amount - self.patient_portion).quantize(Decimal('0.01'))
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
                'payment_status', 'price_list', 'billing_type', 'corporate_client',
                'insurance_provider', 'updated_at'
            ]
            # remove duplicates and non-existent attributes just in case
            update_fields = [f for f in dict.fromkeys(update_fields) if hasattr(self, f)]
            super().save(update_fields=update_fields)

    def get_balance_due(self):
        total_paid = self.payments.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        return D(self.total_amount) - D(total_paid)

    def is_fully_paid(self):
        return self.get_balance_due() <= D('0.00')

    def __str__(self):
        return f"Billing for {getattr(self.request, 'request_id', str(self.pk))} - ₦{self.total_amount}"


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

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        # After saving payment, update billing status
        total_paid = self.billing.payments.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        if D(total_paid) >= D(self.billing.total_amount):
            self.billing.payment_status = 'PAID'
        elif D(total_paid) > D('0.00'):
            self.billing.payment_status = 'PARTIAL'
        else:
            self.billing.payment_status = 'UNPAID'

        # Persist only status (billing totals already maintained in BillingInformation.save)
        self.billing.save(update_fields=['payment_status', 'updated_at'])

    def __str__(self):
        return f"₦{self.amount} - {self.get_payment_method_display()} - {self.payment_date.date()}"


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

    vendor = models.ForeignKey('tenants.Vendor', on_delete=models.CASCADE, related_name='invoices')

    invoice_number = models.CharField(max_length=50, unique=True)
    invoice_date = models.DateField(default=timezone.now)
    due_date = models.DateField()

    insurance_provider = models.ForeignKey(InsuranceProvider, on_delete=models.SET_NULL,
                                           null=True, blank=True, related_name='invoices')
    corporate_client = models.ForeignKey(CorporateClient, on_delete=models.SET_NULL,
                                         null=True, blank=True, related_name='invoices')

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
        Calculate invoice totals from linked billing records.
        Uses billing.insurance_portion (which already includes tax as part of billing.total_amount).
        Also sums billing.tax separately so invoice.tax is explicit if needed.
        """
        # Only include relevant billing types (HMO / CORPORATE)
        qs = self.billing_records.filter(billing_type__in=['HMO', 'CORPORATE'])
        subtotal = qs.aggregate(total=Sum('insurance_portion'))['total'] or Decimal('0.00')
        tax = qs.aggregate(total=Sum('tax'))['total'] or Decimal('0.00')

        self.subtotal = D(subtotal)
        self.tax = D(tax)
        self.total_amount = D(self.subtotal) + D(self.tax)

        # Save core amounts
        self.save(update_fields=['subtotal', 'tax', 'total_amount', 'updated_at'])

    def balance_due(self):
        return D(self.total_amount) - D(self.amount_paid)

    def is_overdue(self):
        return timezone.now().date() > self.due_date and self.status not in ['PAID', 'CANCELLED']

    def __str__(self):
        client = self.insurance_provider or self.corporate_client
        return f"INV-{self.invoice_number} - {client} - ₦{self.total_amount}"


# ==========================================
# 7. INVOICE PAYMENTS
# ==========================================

class InvoicePayment(models.Model):
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


