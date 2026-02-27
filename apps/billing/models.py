"""
billing/models.py

Architecture decisions in this refactor
────────────────────────────────────────
- CorporateClient removed. All third-party billing (HMO, NHIS, CORPORATE wellness)
  flows through InsuranceProvider. CORPORATE is kept as a billing_type label so
  existing data is not orphaned, but it resolves to an InsuranceProvider FK, not
  a separate model.
- max_discount_amount removed from PriceList. Discounts are pure percentages.
- Calculation sequence is now strictly enforced:
    A. Negotiated rate  : subtotal × (1 - price_list.discount_percentage / 100)
    B. Tax              : discounted_amount × (price_list.tax_percentage / 100)
    C. Co-pay split     : final_contract_price × insurance_provider.patient_copay_percentage

Mathematical proof (embedded in _calculate_totals_internal docstring).
"""

import uuid
import logging
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.conf import settings
from django.db import models
from django.db.models import Sum
from django.utils import timezone

logger = logging.getLogger(__name__)


# Safe Decimal helper
def D(value) -> Decimal:
    """Convert any value to a Decimal, quantized to 2 dp. Returns 0.00 on failure."""
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        result = Decimal('0.00')
    return result.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


# ─────────────────────────────────
# 1. PriceList
# ─────────────────────────────────

class PriceList(models.Model):
    PRICE_LIST_TYPES = [
        ('RETAIL',    'Retail'),
        ('HMO',       'HMO/Insurance'),
        ('CORPORATE', 'Corporate / Wellness'),
        ('NHIS',      'NHIS (Government)'),
        ('STAFF',     'Staff Discount'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vendor = models.ForeignKey(
        'tenants.Vendor', on_delete=models.CASCADE, related_name='price_lists'
    )

    name = models.CharField(max_length=100, help_text="e.g. 'Ajinks HMO Rates'")
    price_type = models.CharField(max_length=20, choices=PRICE_LIST_TYPES)

    client_name = models.CharField(
        max_length=200, blank=True, help_text="HMO name or company name"
    )
    contract_number = models.CharField(max_length=100, blank=True)

    # Negotiated rate — applied BEFORE tax (Step A)
    discount_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        help_text="Negotiated rate discount on retail prices (e.g. 10 = 10%)"
    )

    # Applied AFTER discount (Step B)
    tax_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        help_text="Tax % applied after discount (e.g. 7.5)"
    )

    # max_discount_amount intentionally removed — pure % logic only

    allow_overrides = models.BooleanField(
        default=False, help_text="Permit staff to override discount rules"
    )

    effective_date = models.DateField(default=timezone.now)
    expiry_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('vendor', 'name')
        ordering = ['price_type', 'name']

    @property
    def is_expired(self) -> bool:
        if self.expiry_date and self.expiry_date < timezone.now().date():
            return True
        return False

    @property
    def status(self) -> str:
        if not self.is_active:
            return "Inactive"
        if self.is_expired:
            return "Expired"
        return "Active"

    def __str__(self):
        return f"{self.name} ({self.get_price_type_display()})"


# ─────────────────────────────────────────
# 2. InsuranceProvider  (now also covers Corporate / Wellness / NHIS)
# ───────────────────────────────────────────

class InsuranceProvider(models.Model):
    """
    Unified third-party payer model.

    Covers HMOs, NHIS, and corporate self-insured/wellness programs.
    The `provider_type` field distinguishes them in the UI; the billing
    engine treats them identically (price list → discount → tax → co-pay split).
    """

    PROVIDER_TYPES = [
        ('HMO',       'HMO / Private Insurance'),
        ('NHIS',      'NHIS (Government)'),
        ('CORPORATE', 'Corporate / Wellness'),
        ('STAFF',     'Staff (Internal)'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vendor = models.ForeignKey(
        'tenants.Vendor', on_delete=models.CASCADE, related_name='insurance_providers'
    )

    provider_type = models.CharField(
        max_length=20, choices=PROVIDER_TYPES, default='HMO',
        help_text="Category of payer"
    )

    name = models.CharField(max_length=200, help_text="e.g. AVON HMO, Hygeia HMO")
    code = models.CharField(max_length=20, help_text="Short code: AVON, HYG")

    contact_person = models.CharField(max_length=200, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)

    payment_terms_days = models.IntegerField(
        default=30, help_text="Days until payment due"
    )
    credit_limit = models.DecimalField(
        max_digits=14, decimal_places=2, default=0,
        help_text="0 = unlimited credit"
    )

    patient_copay_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        default=Decimal('0.6000'),
        help_text=(
            "Fraction of the Final Contract Price the patient pays at the front desk. "
            "0.6000 = 60% patient / 40% HMO. "
            "Use 1.0000 for full patient responsibility (cash-equivalent). "
            "Use 0.0000 for full HMO coverage."
        )
    )

    is_active = models.BooleanField(default=True)
    requires_preauth = models.BooleanField(
        default=False, help_text="Require pre-authorization for tests"
    )

    # The negotiated price list for this provider
    price_list = models.ForeignKey(
        PriceList, on_delete=models.SET_NULL, null=True, blank=True,
        help_text="Negotiated rate price list for this provider"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        unique_together = [['vendor', 'code']]

    # ── Financial helpers ────────────────────────────────────────────────────

    def get_outstanding_balance(self) -> Decimal:
        """Amount the provider owes the lab (insurance_portion minus what they've paid)."""
        stats = self.billing_records.filter(
            payment_status__in=['UNPAID', 'PARTIAL', 'AUTHORIZED', 'INVOICED', 'OVERDUE']
        ).aggregate(
            total_owed=Sum('insurance_portion'),
            total_paid=Sum('insurance_amount_paid'),
        )
        owed = D(stats['total_owed'] or 0)
        paid = D(stats['total_paid'] or 0)
        return D(owed - paid)

    def is_over_credit_limit(self) -> bool:
        if self.credit_limit <= 0:
            return False  # 0 = unlimited
        return self.get_outstanding_balance() > D(self.credit_limit)

    def get_utilization_percentage(self) -> Decimal:
        if self.credit_limit <= 0:
            return Decimal('0.00')
        return D(
            (self.get_outstanding_balance() / D(self.credit_limit)) * 100
        )

    def __str__(self):
        return f"{self.name} ({self.code})"


# ──────────────────────────────────────────────
# 3. BillingInformation
# ────────────────────────────────────────────

    """
    Financial record for a single TestRequest.

    Calculation hierarchy (enforced in _calculate_totals_internal):
    ┌──────────────────────────────────────────────────────────┐
    │  A. subtotal         = sum of test retail prices         │
    │  B. negotiated_disc  = subtotal × price_list.discount%   │
    │  C. discounted_amt   = subtotal − negotiated_disc        │
    │  D. tax              = discounted_amt × price_list.tax%  │
    │  E. total_amount     = discounted_amt + tax              │  ← Final Contract Price
    │  F. patient_portion  = total_amount × copay_pct          │  ← "Pay to proceed"
    │  G. insurance_portion= total_amount − patient_portion    │  ← "Invoice later"
    └──────────────────────────────────────────────────────────┘

    Proof with sample data:
      Base price    3,000.00
      Discount 10%   −300.00
      Tax 2%          +54.00   (2% of 2,700)
      Contract price 2,754.00
      Patient 60%    1,652.40
      HMO 40%        1,101.60
    """


class BillingInformation(models.Model):

    BILLING_TYPES = [
        ('CASH',      'Cash / Self-Pay'),
        ('HMO',       'HMO / Insurance'),
        ('CORPORATE', 'Corporate / Wellness'),
        ('NHIS',      'NHIS (Government)'),
        ('STAFF',     'Staff (Internal)'),
    ]

    # Insurance-type billing types — all require an InsuranceProvider FK
    INSURANCE_TYPES = {'HMO', 'NHIS', 'CORPORATE', 'STAFF'}

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vendor = models.ForeignKey(
        'tenants.Vendor', on_delete=models.CASCADE, related_name='billing_records'
    )
    request = models.OneToOneField(
        'labs.TestRequest', on_delete=models.CASCADE, related_name='billing_info'
    )

    billing_type = models.CharField(
        max_length=20, choices=BILLING_TYPES, default='CASH'
    )

    # The price list applied to this record (denormalised from InsuranceProvider
    # at creation time so historical records are not affected by future changes)
    price_list = models.ForeignKey(
        PriceList, on_delete=models.SET_NULL, null=True, blank=True,
        help_text="Price list snapshotted at request creation"
    )

    # Single third-party payer FK (replaces both insurance_provider + corporate_client)
    insurance_provider = models.ForeignKey(
        InsuranceProvider, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='billing_records'
    )

    # HMO-specific fields
    policy_number = models.CharField(max_length=100, blank=True)
    pre_authorization_code = models.CharField(max_length=100, blank=True)
    employee_id = models.CharField(max_length=100, blank=True, help_text="Staff / corporate employee ID if applicable")

    # ── Calculated money fields ──────────────────────────────────────────────
    subtotal = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0.00'),
        help_text="Sum of retail test prices before any discount"
    )
    discount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0.00'),
        help_text="Total negotiated discount applied"
    )
    tax = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0.00')
    )
    total_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0.00'),
        help_text="Final Contract Price (subtotal − discount + tax)"
    )

    # Co-pay split (Step C)
    patient_portion = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0.00'),
        help_text="Amount patient pays at the front desk"
    )
    insurance_portion = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0.00'),
        help_text="Amount invoiced to the payer later"
    )

    # ── Staff-adjustable overrides ───────────────────────────────────────────
    manual_discount = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Manual flat-amount discount applied by staff (reduces total before co-pay split)"
    )
    waiver_amount = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Waiver/write-off amount (reduces patient portion post-split)"
    )

    # ── Payment tracking ─────────────────────────────────────────────────────
    patient_amount_paid = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0.00')
    )
    insurance_amount_paid = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0.00')
    )

    referrer = models.ForeignKey('billing.Referrer', on_delete=models.SET_NULL, null=True, blank=True, related_name='billing_records')

    PAYMENT_STATUS = [
        ('UNPAID',     'Unpaid'),
        ('PARTIAL',    'Partially Paid'),
        ('AUTHORIZED', 'Authorized to Proceed'),
        ('PAID',       'Fully Paid'),
        ('INVOICED',   'Invoiced'),
        ('OVERDUE',    'Overdue'),
        ('WAIVED',     'Waived / Written Off'),
    ]
    payment_status = models.CharField(
        max_length=20, choices=PAYMENT_STATUS, default='UNPAID'
    )

    billing_notes = models.TextField(blank=True)

    # Authorisation (admin override / waiver)
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
            models.Index(fields=['vendor', 'insurance_provider']),
        ]

    # ── Calculation engine ───────────────────────────────────────────────────

    def _calculate_totals_internal(self) -> None:
        """
        Enforces the strict billing hierarchy:

          A → negotiated discount
          B → tax on discounted amount
          C → co-pay split

        Portions are LOCKED once any insurance payment has been recorded
        (insurance_amount_paid > 0) to preserve historical accuracy.

        Manual discount and waiver_amount are operational overrides:
          - manual_discount : applied before the co-pay split (reduces contract price)
          - waiver_amount   : applied AFTER the split (reduces patient_portion only)
        """

        # ── Fetch tests ───────────────────────────
        try:
            tests = list(self.request.requested_tests.all())
        except AttributeError:
            tests = []

        if not tests:
            for field in ('subtotal', 'discount', 'tax', 'total_amount',
                          'patient_portion', 'insurance_portion'):
                setattr(self, field, D('0.00'))
            return

        # ── Step A: Build subtotal from the correct price list ───────────────
        running_subtotal = D('0.00')

        for lab_test in tests:
            if self.price_list and callable(getattr(lab_test, 'get_price_from_price_list', None)):
                price = D(lab_test.get_price_from_price_list(self.price_list))
            else:
                price = D(getattr(lab_test, 'price', 0))
            running_subtotal += price

        self.subtotal = running_subtotal

        # ── Step A: Negotiated rate discount (price list %) ──────────────────
        negotiated_discount = D('0.00')
        if self.price_list and self.price_list.discount_percentage:
            negotiated_discount = D(
                running_subtotal * D(self.price_list.discount_percentage) / D(100)
            )

        # Manual flat discount (staff override) — capped at subtotal
        manual_adj = D(self.manual_discount or 0)
        total_discount = min(negotiated_discount + manual_adj, running_subtotal)
        self.discount = total_discount

        discounted_amount = running_subtotal - total_discount

        # ── Step B: Tax on discounted amount ────────────────────────────────
        self.tax = D('0.00')
        if self.price_list and self.price_list.tax_percentage:
            self.tax = D(
                discounted_amount * D(self.price_list.tax_percentage) / D(100)
            )

        # Final Contract Price
        contract_price = discounted_amount + self.tax

        # Apply waiver BEFORE locking (reduces contract price for patient)
        waiver = D(self.waiver_amount or 0)
        effective_contract_price = max(contract_price - waiver, D('0.00'))

        self.total_amount = effective_contract_price

        # ── Step C: Co-pay split ─────────────────────────────────────────────
        #
        # Lock guard: if the insurer has already started paying, do NOT
        # recalculate portions — that would corrupt payment reconciliation.
        #
        if self.insurance_amount_paid > 0:
            # Portions are locked; only total_amount may have changed via waiver.
            # Log a warning so staff are aware.
            logger.warning(
                "BillingInformation pk=%s: portions locked because insurance has "
                "already paid ₦%s. Skipping co-pay split recalculation.",
                self.pk,
                self.insurance_amount_paid,
            )
            return

        if self.billing_type in self.INSURANCE_TYPES and self.insurance_provider:
            # patient_copay_percentage is the fraction of contract price the patient owes.
            # Example: 0.6000 → patient pays 60%, insurer pays 40%
            copay_rate = D(
                getattr(self.insurance_provider, 'patient_copay_percentage', D('1.0000'))
            )
            # Clamp to [0, 1] to guard against bad data
            copay_rate = max(D('0.00'), min(D('1.00'), copay_rate))

            self.patient_portion = D(effective_contract_price * copay_rate)
            self.insurance_portion = D(effective_contract_price - self.patient_portion)

        else:
            # CASH or insurance provider missing → patient is responsible for everything
            self.patient_portion = effective_contract_price
            self.insurance_portion = D('0.00')

    # ── Save ────────────────────────────────────

    def save(self, *args, **kwargs):
        """
        Always recalculate before persisting.

        For existing records, explicitly list update_fields to avoid
        accidentally overwriting fields managed by other processes
        (e.g. payment_status updated by Payment.save()).
        """
        self._calculate_totals_internal()

        if not self.pk:
            # New record — full INSERT
            super().save(*args, **kwargs)
        else:
            # Existing record — explicit UPDATE to avoid partial overwrites
            update_fields = [
                'subtotal', 'discount', 'manual_discount', 'waiver_amount',
                'tax', 'total_amount',
                'patient_portion', 'insurance_portion',
                'patient_amount_paid', 'insurance_amount_paid',
                'payment_status',
                'price_list', 'billing_type',
                'insurance_provider',
                'policy_number', 'pre_authorization_code', 'employee_id',
                'billing_notes',
                'authorized_by', 'authorized_at', 'authorization_reason',
                'updated_at',
            ]
            # Guard: only include fields that exist on the model instance
            update_fields = [
                f for f in dict.fromkeys(update_fields) if hasattr(self, f)
            ]
            super().save(update_fields=update_fields)

    # ── Status helpers ───────────────────────────────────────────────────────

    @property
    def is_payment_cleared(self) -> bool:
        """
        Returns True when the lab can proceed with sample collection.

        CASH    → patient must have fully paid
        HMO     → patient must have paid their co-pay portion
        NHIS    → same as HMO
        CORPORATE / STAFF → authorised to proceed on account (company pays via invoice)
        AUTHORIZED / WAIVED → always cleared
        """
        if self.payment_status in ('PAID', 'AUTHORIZED', 'WAIVED'):
            return True

        if self.billing_type in ('HMO', 'NHIS'):
            return self.patient_amount_paid >= self.patient_portion

        if self.billing_type in ('CORPORATE', 'STAFF'):
            # Proceed once the billing record is established; company pays later
            return True

        return False

    def update_payment_status(self) -> None:
        """
        Derive payment_status from actual payment totals.
        Call this after recording any Payment against this record.
        """
        total_paid = self.patient_amount_paid + self.insurance_amount_paid

        if total_paid >= self.total_amount and self.total_amount > 0:
            self.payment_status = 'PAID'
        elif self.insurance_amount_paid > 0 or self.patient_amount_paid > 0:
            self.payment_status = 'PARTIAL'
        # Do not downgrade AUTHORIZED / WAIVED records
        # elif self.payment_status not in ('AUTHORIZED', 'WAIVED', 'INVOICED'):
        elif self.payment_status not in ('AUTHORIZED', 'WAIVED'):
            self.payment_status = 'UNPAID'

        self.save(update_fields=['payment_status', 'updated_at'])

    def get_balance_due(self) -> Decimal:
        """Balance based on actual Payment records (source of truth)."""
        total_paid = (
            self.payments.aggregate(total=Sum('amount'))['total']
            or Decimal('0.00')
        )
        return D(self.total_amount) - D(total_paid)

    def is_fully_paid(self) -> bool:
        if self.payment_status in ('PAID', 'WAIVED'):
            return True
        if self.total_amount > 0:
            return self.get_balance_due() <= 0
        return False

    def __str__(self):
        return (
            f"Billing for {getattr(self.request, 'request_id', str(self.pk))} "
            f"— ₦{self.total_amount}"
        )


# ────────────────────────────────────────
# 4. Invoice  (HMO / Corporate — bills the insurance_portion in bulk)
# ─────────────────────────────────────────────

class Invoice(models.Model):
    INVOICE_STATUS = [
        ('DRAFT',     'Draft'),
        ('SENT',      'Sent'),
        ('PARTIAL',   'Partially Paid'),
        ('PAID',      'Paid'),
        ('OVERDUE',   'Overdue'),
        ('CANCELLED', 'Cancelled'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vendor = models.ForeignKey(
        'tenants.Vendor', on_delete=models.CASCADE, related_name='invoices'
    )

    invoice_number = models.CharField(max_length=50, unique=True)
    invoice_date = models.DateField(default=timezone.now)
    due_date = models.DateField()

    # Single payer FK — covers HMO, NHIS, Corporate, Staff
    insurance_provider = models.ForeignKey(
        InsuranceProvider, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='invoices'
    )

    period_start = models.DateField()
    period_end = models.DateField()

    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    tax = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0.00'),
        help_text="Sum of insurance_portion across all attached billing records"
    )
    amount_paid = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))

    status = models.CharField(max_length=20, choices=INVOICE_STATUS, default='DRAFT')

    billing_records = models.ManyToManyField(BillingInformation, related_name='invoices')

    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-invoice_date']
        indexes = [
            models.Index(fields=['vendor', 'status']),
            models.Index(fields=['due_date']),
        ]

    def calculate_totals(self) -> None:
        """
        Sum the insurance_portion from all attached billing records.
        This is what the payer owes — patient portions are excluded.
        """
        agg = self.billing_records.aggregate(
            ins_total=Sum('insurance_portion'),
            tax_total=Sum('tax'),
        )
        self.total_amount = D(agg['ins_total'] or 0)
        self.tax = D(agg['tax_total'] or 0)
        self.save(update_fields=['total_amount', 'tax', 'updated_at'])

    def add_billing_records(self, record_ids: list) -> None:
        """
        Attach eligible billing records to this invoice and mark them INVOICED.

        Eligibility:
          - Must be in the selected id list
          - payment_status in UNPAID / PARTIAL / AUTHORIZED
          - Must belong to this invoice's insurance_provider
          - insurance_portion must be > 0 (nothing to bill otherwise)
        """
        eligible = BillingInformation.objects.filter(
            id__in=record_ids,
            insurance_provider=self.insurance_provider,
            insurance_portion__gt=0,
            payment_status__in=['UNPAID', 'PARTIAL', 'AUTHORIZED'],
        )

        if eligible.exists():
            self.billing_records.add(*eligible)
            eligible.update(payment_status='INVOICED')
            self.calculate_totals()

    def balance_due(self) -> Decimal:
        return D(self.total_amount) - D(self.amount_paid)

    def is_overdue(self) -> bool:
        return (
            timezone.now().date() > self.due_date
            and self.status not in ('PAID', 'CANCELLED')
        )

    def __str__(self):
        payer = self.insurance_provider or "Unknown Payer"
        return f"{self.invoice_number} — {payer} — ₦{self.total_amount}"


# ──────────────────
# 5. Payment  (patient / cash payments against BillingInformation)
# ─────────────

class Payment(models.Model):
    PAYMENT_METHODS = [
        ('CASH',     'Cash'),
        ('POS',      'POS (Card)'),
        ('TRANSFER', 'Bank Transfer'),
        ('CHEQUE',   'Cheque'),
        ('MOBILE',   'Mobile Money'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    billing = models.ForeignKey(
        BillingInformation, on_delete=models.CASCADE, related_name='payments'
    )

    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS)
    transaction_reference = models.CharField(
        max_length=100, blank=True, help_text="POS ref, transfer ref, etc."
    )
    payment_date = models.DateTimeField(default=timezone.now)
    collected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-payment_date']
        
    def save(self, *args, **kwargs):
        # 1. Track if this is a new payment before saving
        is_new = self._state.adding 
        
        # 2. Save the payment record first
        super().save(*args, **kwargs)

        # 3. RECOMPUTE BILLING STATUS (Existing Logic)
        # We aggregate all payments associated with this billing record
        from django.db.models import Sum
        
        total_paid_data = self.billing.payments.aggregate(total=Sum('amount'))['total']
        total_paid_d = D(total_paid_data or '0.00')
        total_amt = D(self.billing.total_amount)

        # Determine new status
        if total_amt > 0 and total_paid_d >= total_amt:
            new_status = 'PAID'
        elif total_paid_d > 0:
            new_status = 'PARTIAL'
        elif self.billing.payment_status not in ('AUTHORIZED', 'WAIVED'):
            new_status = 'UNPAID'
        else:
            new_status = self.billing.payment_status

        # Update the parent billing record
        self.billing.patient_amount_paid = total_paid_d
        self.billing.payment_status = new_status
        self.billing.save(update_fields=['patient_amount_paid', 'payment_status', 'updated_at'])

        # 4. REBATE CALCULATION (New Logic)
        # We only calculate rebates on the FIRST save of a payment to avoid duplicates
        if is_new and self.billing.referrer:
            referrer = self.billing.referrer
            
            # Use the method from your Referrer model
            earned_amount = referrer.calculate_rebate(self.amount)
            
            if earned_amount > 0:
                # Assuming RebateRecord is imported or available in the namespace
                from referral.models import RebateRecord 
                RebateRecord.objects.create(
                    vendor=self.billing.vendor, # For multi-tenant filtering
                    referrer=referrer,
                    billing=self.billing,
                    payment=self,
                    rebate_amount=earned_amount,
                    status='UNPAID'
                )

    def __str__(self):
        return f"₦{self.amount} — {self.get_payment_method_display()} — {self.payment_date.date()}"
    
    # def save(self, *args, **kwargs):
    #     super().save(*args, **kwargs)

    #     # Recompute payment_status from the live payment ledger
    #     total_paid = (
    #         self.billing.payments.aggregate(total=Sum('amount'))['total']
    #         or Decimal('0.00')
    #     )
    #     total_amt = D(self.billing.total_amount)
    #     total_paid_d = D(total_paid)

    #     if total_amt > 0 and total_paid_d >= total_amt:
    #         new_status = 'PAID'
    #     elif total_paid_d > 0:
    #         new_status = 'PARTIAL'
    #     elif self.billing.payment_status not in ('AUTHORIZED', 'WAIVED'):
    #         new_status = 'UNPAID'
    #     else:
    #         new_status = self.billing.payment_status  # preserve AUTHORIZED / WAIVED

    #     self.billing.patient_amount_paid = total_paid_d
    #     self.billing.payment_status = new_status
    #     self.billing.save(update_fields=['patient_amount_paid', 'payment_status', 'updated_at'])


    # def __str__(self):
    #     return (
    #         f"₦{self.amount} — {self.get_payment_method_display()} "
    #         f"— {self.payment_date.date()}"
    #     )


# ─────────────────────────────────────────────
# 6. InvoicePayment  (bulk payments from payers against an Invoice)
# ────────────────────────────────────────────────────

class InvoicePayment(models.Model):
    PAYMENT_METHODS = [
        ('TRANSFER', 'Bank Transfer'),
        ('CHEQUE',   'Cheque'),
        ('CASH',     'Cash'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice = models.ForeignKey(
        Invoice, on_delete=models.CASCADE, related_name='payments'
    )

    amount = models.DecimalField(max_digits=14, decimal_places=2)
    payment_date = models.DateField(default=timezone.now)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS)
    reference_number = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)

    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True
    )
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-payment_date']

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        # Update invoice totals and propagate to individual billing records
        total_paid = (
            self.invoice.payments.aggregate(total=Sum('amount'))['total']
            or Decimal('0.00')
        )
        self.invoice.amount_paid = D(total_paid)

        if D(total_paid) >= D(self.invoice.total_amount) and self.invoice.total_amount > 0:
            self.invoice.status = 'PAID'
        elif D(total_paid) > 0:
            self.invoice.status = 'PARTIAL'

        self.invoice.save(update_fields=['amount_paid', 'status', 'updated_at'])

        # Propagate insurance payment back to individual billing records
        # so insurance_amount_paid stays accurate for reconciliation reports
        self._propagate_to_billing_records(D(total_paid))

    def _propagate_to_billing_records(self, total_invoice_paid: Decimal) -> None:
        """
        Distribute the invoice payment proportionally across attached billing records.

        Uses each record's share of the invoice total as the allocation weight.
        This ensures insurance_amount_paid on each BillingInformation is accurate
        for per-patient reconciliation without double-counting.
        """
        # invoice_total = D(self.invoice.total_amount)
        # if invoice_total <= 0:
        #     return

        # records = self.invoice.billing_records.all()
        # for record in records:
        #     if invoice_total > 0:
        #         share = D(record.insurance_portion) / invoice_total
        #     else:
        #         share = D('0.00')
        

        #     record.insurance_amount_paid = D(total_invoice_paid * share)
        #     record.save(update_fields=['insurance_amount_paid', 'updated_at'])

        invoice_total = D(self.invoice.total_amount)
        if invoice_total <= 0:
            return

        records = self.invoice.billing_records.all()
        for record in records:
            share = (
                D(record.insurance_portion) / invoice_total
                if invoice_total > 0 else D('0.00')
            )
            record.insurance_amount_paid = D(total_invoice_paid * share)

            # Derive the correct payment_status from the updated totals.
            # Do NOT call update_payment_status() here — it issues its own
            # save() and would double-hit the DB. Compute inline instead.
            total_paid = (
                D(record.patient_amount_paid or 0) +
                record.insurance_amount_paid
            )
            if total_paid >= D(record.total_amount) and D(record.total_amount) > 0:
                new_status = 'PAID'
            elif total_paid > 0:
                new_status = 'PARTIAL'
            else:
                new_status = 'INVOICED'

            record.payment_status = new_status
            record.save(update_fields=[
                'insurance_amount_paid',
                'payment_status',
                'updated_at',
            ])

    def __str__(self):
        return f"₦{self.amount} — {self.invoice.invoice_number} — {self.payment_date}"


# 7. REBATE MODELS

class Referrer(models.Model):
    REBATE_TYPE_CHOICES = [
        ('PERCENTAGE', 'Percentage of Amount Collected'),
        ('FIXED',      'Fixed Amount per Request'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vendor = models.ForeignKey(
        'tenants.Vendor', on_delete=models.CASCADE,
        related_name='referrers'
    )

    # ── Identity ──────────────────────────────────────────────────────────
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=50, blank=True,help_text="Short internal code e.g. GHC, RHA")
    contact_person = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)

    # ── Rebate agreement ──────────────────────────────────────────────────
    rebate_type = models.CharField(
        max_length=20, choices=REBATE_TYPE_CHOICES, default='PERCENTAGE',
    )
    rebate_value = models.DecimalField(
        max_digits=12, decimal_places=2, default=D('0.00'),
        help_text=(
            "10.00 = 10% of amount collected (PERCENTAGE), "
            "or ₦500.00 flat per request (FIXED)"
        )
    )

    # ── Payment details (for settlement) ─────────────────────────────────
    bank_name = models.CharField(max_length=100, blank=True)
    account_number = models.CharField(max_length=20, blank=True)
    account_name = models.CharField(max_length=200, blank=True)
    payment_terms_days = models.IntegerField(
        default=30, help_text="Days after statement date when payment is due"
    )

    is_active  = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [['vendor', 'code']]
        ordering        = ['name']
        indexes         = [models.Index(fields=['vendor', 'is_active'])]

    def __str__(self):
        return f"{self.name} ({self.code or self.get_rebate_type_display()})"

    # ── Core calculation ──────────────────────────────────────────────────

    def calculate_rebate(self, payment_basis: D) -> D:
        """
        Calculate the rebate earned for a given payment_basis amount.

        payment_basis = the amount the lab actually collected for one
        billing record (patient_amount_paid + insurance_amount_paid).

        Always rounds to 2 decimal places using ROUND_HALF_UP.
        Returns 0 if the referrer or value is inactive / zero.
        """
        if not self.is_active or self.rebate_value <= 0 or payment_basis <= 0:
            return D('0.00')

        if self.rebate_type == 'PERCENTAGE':
            raw = payment_basis * (self.rebate_value / D('100'))
        else:
            raw = self.rebate_value

        return raw.quantize(D('0.01'), rounding=ROUND_HALF_UP)

    # ── Reporting helpers ─────────────────────────────────────────────────

    def get_unpaid_balance(self) -> D:
        """Total rebate owed to this referrer (unpaid RebateRecords)."""
        result = self.rebate_records.filter(
            status='UNPAID'
        ).aggregate(total=Sum('rebate_amount'))
        return D(result['total'] or 0).quantize(D('0.01'))

    def get_lifetime_earned(self) -> D:
        """Total rebate ever earned (all statuses)."""
        result = self.rebate_records.aggregate(total=Sum('rebate_amount'))
        return D(result['total'] or 0).quantize(D('0.01'))


# ──────────────────────────────────────

class RebateRecord(models.Model):
    """
    Immutable ledger entry: one row per billing record that earned a rebate.

    Created automatically by a signal when a billing record's payment
    clears (is_payment_cleared == True). Never modified after creation
    except for status transitions: UNPAID → PAID (when settled).

    OneToOneField on billing prevents duplicate rebate records.
    """

    STATUS_CHOICES = [
        ('UNPAID',   'Unpaid — Pending Settlement'),
        ('INCLUDED', 'Included in a Statement'),
        ('PAID',     'Paid — Settlement Complete'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    referrer = models.ForeignKey(
        Referrer, on_delete=models.PROTECT,
        related_name='rebate_records',
        help_text="Partner hospital this rebate is owed to"
    )
    billing  = models.OneToOneField(
        'billing.BillingInformation',
        on_delete=models.PROTECT,
        related_name='rebate_record',
        help_text="The billing record that generated this rebate"
    )
    settlement = models.ForeignKey(
        'billing.RebateSettlement',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='rebate_records',
        help_text="The settlement batch this was paid in (null until settled)"
    )

    # ── Financial ─────────────────────────────────────────────────────────
    payment_basis  = models.DecimalField(
        max_digits=14, decimal_places=2,
        help_text="Amount collected from patient + insurance at calculation time"
    )
    rebate_amount  = models.DecimalField(
        max_digits=12, decimal_places=2,
        help_text="Actual rebate earned (calculated, then frozen)"
    )
    rebate_type    = models.CharField(max_length=20)   # snapshot of agreement at time
    rebate_value   = models.DecimalField(max_digits=12, decimal_places=2)  # snapshot

    status     = models.CharField(max_length=20, choices=STATUS_CHOICES, default='UNPAID')
    earned_at  = models.DateTimeField(default=timezone.now,
                                      help_text="When payment cleared and rebate was earned")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-earned_at']
        indexes  = [
            models.Index(fields=['referrer', 'status']),
            models.Index(fields=['earned_at']),
        ]

    def __str__(self):
        return (
            f"Rebate ₦{self.rebate_amount} → {self.referrer.name} "
            f"[{self.billing_id}] ({self.status})"
        )


# ─────────────────────────────────────────────────

class RebateSettlement(models.Model):
    """
    A settlement batch: groups unpaid RebateRecords into a single payment run.

    Mirrors the Invoice model structure so the workflow is familiar:
      DRAFT → APPROVED → PAID → (CANCELLED)

    The lab creates a statement (DRAFT), reviews it, approves it, then records
    the bank transfer to the referrer and marks it PAID.
    """

    STATUS_CHOICES = [
        ('DRAFT',     'Draft'),
        ('APPROVED',  'Approved — Awaiting Payment'),
        ('PAID',      'Paid'),
        ('CANCELLED', 'Cancelled'),
    ]

    id       = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vendor   = models.ForeignKey(
        'tenants.Vendor', on_delete=models.CASCADE,
        related_name='rebate_settlements'
    )
    referrer = models.ForeignKey(
        Referrer, on_delete=models.PROTECT,
        related_name='settlements'
    )

    statement_number = models.CharField(max_length=50, unique=True)
    period_start     = models.DateField()
    period_end       = models.DateField()

    total_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=D('0.00'),
        help_text="Sum of all RebateRecord.rebate_amount in this batch"
    )
    record_count = models.IntegerField(default=0)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')

    # Payment proof (filled in when PAID)
    payment_date      = models.DateField(null=True, blank=True)
    payment_reference = models.CharField(max_length=100, blank=True)
    payment_method    = models.CharField(max_length=50, blank=True)

    notes      = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.statement_number} — {self.referrer.name} — ₦{self.total_amount}"

    def recalculate_totals(self):
        """Recompute total_amount and record_count from attached RebateRecords."""
        from django.db.models import Sum, Count
        agg = self.rebate_records.aggregate(
            total=Sum('rebate_amount'),
            count=Count('id'),
        )
        self.total_amount = D(agg['total'] or 0).quantize(D('0.01'))
        self.record_count = agg['count'] or 0
        self.save(update_fields=['total_amount', 'record_count', 'updated_at'])


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



# # class Payment(models.Model):
# #     """
# #     Records individual payment transactions for billing records.
# #     Supports multiple payment methods and partial payments.
# #     """
    
# #     vendor = models.ForeignKey(
# #         'tenants.Vendor',
# #         on_delete=models.CASCADE,
# #         related_name='payments'
# #     )
    
# #     billing = models.ForeignKey(
# #         'billing.BillingInformation',
# #         on_delete=models.CASCADE,
# #         related_name='payments'
# #     )
    
# #     # Payment Details
# #     amount = models.DecimalField(
# #         max_digits=12,
# #         decimal_places=2,
# #         help_text="Amount paid in this transaction"
# #     )
    
# #     PAYMENT_METHODS = [
# #         ('cash', 'Cash'),
# #         ('bank_transfer', 'Bank Transfer'),
# #         ('pos', 'POS/Card Payment'),
# #         ('cheque', 'Cheque'),
# #         ('mobile_money', 'Mobile Money (e.g., PayStack, Flutterwave)'),
# #         ('online', 'Online Payment Gateway'),
# #         ('insurance_claim', 'Insurance Claim Settlement'),
# #         ('corporate_invoice', 'Corporate Invoice Payment'),
# #     ]
# #     payment_method = models.CharField(
# #         max_length=30,
# #         choices=PAYMENT_METHODS,
# #         default='cash'
# #     )
    
# #     # Transaction tracking
# #     transaction_reference = models.CharField(
# #         max_length=200,
# #         blank=True,
# #         help_text="Bank reference, POS receipt number, or payment gateway transaction ID"
# #     )
    
# #     receipt_number = models.CharField(
# #         max_length=100,
# #         unique=True,
# #         editable=False,
# #         help_text="Internal receipt number generated by system"
# #     )
    
# #     # For cheques
# #     cheque_number = models.CharField(max_length=50, blank=True)
# #     cheque_bank = models.CharField(max_length=100, blank=True)
# #     cheque_date = models.DateField(null=True, blank=True)
    
# #     # Status tracking
# #     PAYMENT_STATUS = [
# #         ('pending', 'Pending Verification'),
# #         ('completed', 'Completed'),
# #         ('failed', 'Failed'),
# #         ('reversed', 'Reversed/Refunded'),
# #         ('cheque_bounced', 'Cheque Bounced'),
# #     ]
# #     status = models.CharField(
# #         max_length=20,
# #         choices=PAYMENT_STATUS,
# #         default='completed'
# #     )
    
# #     # Staff tracking
# #     received_by = models.ForeignKey(
# #         settings.AUTH_USER_MODEL,
# #         on_delete=models.SET_NULL,
# #         null=True,
# #         related_name='payments_received',
# #         help_text="Staff member who received/confirmed payment"
# #     )
    
# #     verified_by = models.ForeignKey(
# #         settings.AUTH_USER_MODEL,
# #         on_delete=models.SET_NULL,
# #         null=True,
# #         blank=True,
# #         related_name='payments_verified',
# #         help_text="Staff member who verified payment (for bank transfers)"
# #     )
    
# #     # Timestamps
# #     payment_date = models.DateTimeField(
# #         default=timezone.now,
# #         help_text="When payment was received"
# #     )
    
# #     verified_at = models.DateTimeField(
# #         null=True,
# #         blank=True,
# #         help_text="When payment was verified (for online/transfer payments)"
# #     )
    
# #     created_at = models.DateTimeField(auto_now_add=True)
# #     updated_at = models.DateTimeField(auto_now=True)
    
# #     # Notes
# #     payment_notes = models.TextField(
# #         blank=True,
# #         help_text="Additional notes about this payment"
# #     )
    
# #     class Meta:
# #         ordering = ['-payment_date']
# #         indexes = [
# #             models.Index(fields=['vendor', 'payment_date']),
# #             models.Index(fields=['billing', 'status']),
# #             models.Index(fields=['receipt_number']),
# #         ]
    
# #     def save(self, *args, **kwargs):
# #         """Generate receipt number if not exists"""
# #         if not self.receipt_number:
# #             # Generate unique receipt number
# #             last_payment = Payment.objects.filter(
# #                 vendor=self.vendor
# #             ).order_by('-id').first()
            
# #             if last_payment and last_payment.receipt_number:
# #                 try:
# #                     last_num = int(last_payment.receipt_number.split('-')[-1])
# #                     new_num = last_num + 1
# #                 except (ValueError, IndexError):
# #                     new_num = 1
# #             else:
# #                 new_num = 1
            
# #             self.receipt_number = f"RCP-{self.vendor.id}-{new_num:08d}"
        
# #         super().save(*args, **kwargs)
    
# #     def __str__(self):
# #         return f"Payment {self.receipt_number} - ₦{self.amount} ({self.get_payment_method_display()})"

