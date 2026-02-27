from datetime import datetime, timedelta, date
from django.utils import timezone
from datetime import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy, reverse
from django.utils import timezone
from django.views.generic import (
 View
)

from decimal import Decimal
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Sum, Count, Avg, Case, When, DecimalField, F, Value
    
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from datetime import datetime
from ..models import BillingInformation, Payment, InsuranceProvider, Invoice, D
from ..forms import BillingInformationForm, BillingFilterForm, PaymentForm
from apps.accounts.decorators import require_capability

from django.utils import timezone
# from decimal import Decimal as D


"""
billing/views.py — BillingDashboardView and billing_list_view

Bugs fixed:
──────────────────────────────────────────────────────────────────────────────
1.  [DASHBOARD] corporate_client removed from select_related
2.  [DASHBOARD] vendor guard added — AttributeError if user has no vendor
3.  [DASHBOARD] total_revenue now sums patient_amount_paid + insurance_amount_paid
    (actual collected cash), not total_amount (which includes uncollected portions)
4.  [DASHBOARD] outstanding_balance split into patient_outstanding and
    insurance_outstanding so the dashboard can show meaningful numbers per party
5.  [LIST] datetime.strftime → datetime.strptime (strftime formats, strptime parses)
6.  [LIST] date_to was parsing date_from by mistake (copy-paste bug) — fixed
7.  [LIST] provider filter now only queries insurance_provider_id (corporate_client
    FK no longer exists)
8.  [LIST] CorporateClient queryset and context key removed
9.  [LIST] corporate_client removed from select_related
10. [LIST] insurance_providers queryset passed to context for filter dropdown
"""



# ───────────────────
# Dashboard
# ──────────────────────────────
"""
billing/views.py — BillingDashboardView

Fix: TemplateSyntaxError from non-existent 'multiply' and 'divide' template filters.
Django's template engine only supports basic arithmetic via the 'add' filter.
Any calculation beyond addition must happen in the view, not the template.

Additional metrics pre-calculated here so the template only renders values:
  - collection_rate_pct   : revenue / (revenue + outstanding) × 100
  - patient_collection_pct: patient_amount_paid / patient_portion × 100
  - insurance_collection_pct: insurance_amount_paid / insurance_portion × 100
  - avg_billing_amount    : total_amount / number of billing records
"""


class BillingDashboardView(LoginRequiredMixin, View):
    template_name = 'billing/dashboard1.html'

    def get(self, request):
        vendor = getattr(request.user, 'vendor', None)
        if vendor is None:
            raise PermissionDenied("Only vendor accounts can access the billing dashboard.")

        # ── Date range filter ────────────────────────────────────────────────
        range_opt = request.GET.get('range', 'this_month')
        today = timezone.now().date()

        if range_opt == 'today':
            start_date = end_date = today

        elif range_opt == 'this_week':
            start_date = today - timedelta(days=today.weekday())  # Monday
            end_date = today

        elif range_opt == 'last_month':
            first_of_this_month = today.replace(day=1)
            last_month_end = first_of_this_month - timedelta(days=1)
            start_date = last_month_end.replace(day=1)
            end_date = last_month_end

        elif range_opt == 'this_quarter':
            quarter = (today.month - 1) // 3 + 1
            start_month = 3 * quarter - 2
            start_date = date(today.year, start_month, 1)
            end_date = today

        elif range_opt == 'this_year':
            start_date = date(today.year, 1, 1)
            end_date = today

        else:  # default: this_month
            start_date = today.replace(day=1)
            end_date = today

        billing_qs = BillingInformation.objects.filter(
            vendor=vendor,
            created_at__date__range=[start_date, end_date],
        )

        # ── Revenue: actual cash collected, not contract value ───────────────
        collected = billing_qs.aggregate(
            patient_collected=Sum('patient_amount_paid'),
            insurance_collected=Sum('insurance_amount_paid'),
        )
        total_revenue = (
            D(collected['patient_collected'] or 0)
            + D(collected['insurance_collected'] or 0)
        )

        # ── Outstanding: split by party ──────────────────────────────────────
        outstanding = billing_qs.filter(
            payment_status__in=['UNPAID', 'PARTIAL', 'AUTHORIZED', 'INVOICED', 'OVERDUE'],
        ).aggregate(
            patient_owed=Sum('patient_portion'),
            patient_paid=Sum('patient_amount_paid'),
            insurance_owed=Sum('insurance_portion'),
            insurance_paid=Sum('insurance_amount_paid'),
        )
        patient_outstanding = max(
            D(outstanding['patient_owed'] or 0) - D(outstanding['patient_paid'] or 0),
            D('0.00'),
        )
        insurance_outstanding = max(
            D(outstanding['insurance_owed'] or 0) - D(outstanding['insurance_paid'] or 0),
            D('0.00'),
        )
        total_outstanding = patient_outstanding + insurance_outstanding

        # ── Unpaid payer invoices ────────────────────────────────────────────
        unpaid_invoices = D(
            Invoice.objects.filter(
                vendor=vendor,
                status__in=['SENT', 'OVERDUE'],
            ).aggregate(total=Sum('total_amount'))['total'] or 0
        )

        # Collection rate = revenue collected / (revenue + outstanding) × 100
        # Answers: "Of all money owed to us in this period, what % have we collected?"
        collection_denominator = total_revenue + total_outstanding
        collection_rate_pct = (
            round(float(total_revenue / collection_denominator) * 100, 1)
            if collection_denominator > 0 else 0.0
        )

        # Patient collection rate = patient_paid / patient_portion × 100
        total_patient_portion = D(
            billing_qs.aggregate(s=Sum('patient_portion'))['s'] or 0
        )
        patient_collection_pct = (
            round(float(
                D(collected['patient_collected'] or 0) / total_patient_portion
            ) * 100, 1)
            if total_patient_portion > 0 else 0.0
        )

        # Insurance collection rate = insurance_paid / insurance_portion × 100
        total_insurance_portion = D(
            billing_qs.aggregate(s=Sum('insurance_portion'))['s'] or 0
        )
        insurance_collection_pct = (
            round(float(
                D(collected['insurance_collected'] or 0) / total_insurance_portion
            ) * 100, 1)
            if total_insurance_portion > 0 else 0.0
        )

        # Average billing amount across the period
        avg_billing = D(
            billing_qs.aggregate(avg=Avg('total_amount'))['avg'] or 0
        )

        # Total contract value (sum of all billing records in range)
        total_contract_value = D(
            billing_qs.aggregate(s=Sum('total_amount'))['s'] or 0
        )

        # ── Recent billing records ───────────────────────────────────────────
        recent_billings = (
            billing_qs
            .select_related('request', 'request__patient', 'insurance_provider')
            .prefetch_related('payments')
            .order_by('-created_at')[:10]
        )
 
        # ── Breakdown tables ──────────────────────────────────
        payment_breakdown = billing_qs.values('payment_status').annotate(
            count=Count('id'),
            total=Sum('total_amount'),
        ).order_by('payment_status')

        billing_breakdown = billing_qs.values('billing_type').annotate(
            count=Count('id'),
            total=Sum('total_amount'),
        ).order_by('billing_type')

        context = {
            # Filter state
            'range':      range_opt,
            'start_date': start_date,
            'end_date':   end_date,

            # ── Core financial metrics ───────────────────────────────────────
            'total_revenue':          total_revenue,
            'total_contract_value':   total_contract_value,
            'avg_billing':            avg_billing,

            # Outstanding split by party
            'patient_outstanding':    patient_outstanding,
            'insurance_outstanding':  insurance_outstanding,
            'total_outstanding':      total_outstanding,

            # Unpaid payer invoices
            'unpaid_invoices':        unpaid_invoices,

            # ── Pre-calculated rates (use directly in template, no arithmetic needed) ─
            # FIX: these replace the invalid {{ value|multiply:100|divide:x }} calls
            'collection_rate_pct':       collection_rate_pct,       # e.g. 73.4
            'patient_collection_pct':    patient_collection_pct,    # e.g. 88.2
            'insurance_collection_pct':  insurance_collection_pct,  # e.g. 41.0

            # ── Breakdown data ───────────────────────────────────────────────
            'payment_breakdown':  payment_breakdown,
            'billing_breakdown':  billing_breakdown,
            'recent_billings':    recent_billings,
        }

        return render(request, self.template_name, context)


# ─────────────────────
# Billing List
# ──────────────────────────

@login_required
def billing_list_view(request):
    """
    Filterable, searchable, paginated billing record list.

    Filters:
      - Full-text search (request ID, patient name, policy number, employee ID)
      - Billing type
      - Payment status
      - Date range (created_at)
      - Insurance / corporate provider
    """
    vendor = getattr(request.user, 'vendor', None)
    if vendor is None:
        raise PermissionDenied("Only vendor accounts can access billing records.")

    queryset = (
        BillingInformation.objects
        .filter(vendor=vendor)
        .select_related(
            'request',
            'request__patient',
            'price_list',
            'insurance_provider',   # covers HMO, NHIS, Corporate, Staff
        )
    )

    # ── Search ───────────────────────────────────────────────────────────────
    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(
            Q(request__request_id__icontains=q)        |
            Q(request__patient__first_name__icontains=q) |
            Q(request__patient__last_name__icontains=q)  |
            Q(policy_number__icontains=q)               |
            Q(employee_id__icontains=q)
        )

    # ── Filters ──────────────────────────────────────────────────────────────
    billing_type = request.GET.get('billing_type', '').strip()
    if billing_type:
        queryset = queryset.filter(billing_type=billing_type)

    payment_status = request.GET.get('payment_status', '').strip()
    if payment_status:
        queryset = queryset.filter(payment_status=payment_status)

    # Date parsing — strptime parses a string into a date; strftime formats a date
    # into a string. The original code had these backwards.
    date_from_str = request.GET.get('date_from', '').strip()
    if date_from_str:
        try:
            date_from_obj = datetime.strptime(date_from_str, '%Y-%m-%d').date()
            queryset = queryset.filter(created_at__date__gte=date_from_obj)
        except ValueError:
            pass  # silently ignore malformed date rather than crashing

    date_to_str = request.GET.get('date_to', '').strip()
    if date_to_str:
        try:
            date_to_obj = datetime.strptime(date_to_str, '%Y-%m-%d').date()
            queryset = queryset.filter(created_at__date__lte=date_to_obj)
        except ValueError:
            pass

    # Provider filter — insurance_provider only; corporate_client FK no longer exists
    provider_id = request.GET.get('provider', '').strip()
    if provider_id:
        queryset = queryset.filter(insurance_provider_id=provider_id)

    # ── Summary statistics ───────────────────────────────────────────────────
    summary = queryset.aggregate(
        total_billings=Count('id'),
        total_amount_sum=Sum('total_amount'),
        unpaid_amount=Sum(
            Case(
                When(payment_status='UNPAID', then=F('total_amount')),
                default=Value(0),
                output_field=DecimalField(max_digits=14, decimal_places=2),
            )
        ),
        paid_amount=Sum(
            Case(
                When(payment_status='PAID', then=F('patient_amount_paid') + F('insurance_amount_paid')),
                default=Value(0),
                output_field=DecimalField(max_digits=14, decimal_places=2),
            )
        ),
        # Patient-side outstanding
        patient_outstanding=Sum(
            Case(
                When(
                    payment_status__in=['UNPAID', 'PARTIAL', 'AUTHORIZED'],
                    then=F('patient_portion') - F('patient_amount_paid'),
                ),
                default=Value(0),
                output_field=DecimalField(max_digits=14, decimal_places=2),
            )
        ),
        # Insurance-side outstanding
        insurance_outstanding=Sum(
            Case(
                When(
                    payment_status__in=['UNPAID', 'PARTIAL', 'AUTHORIZED', 'INVOICED'],
                    then=F('insurance_portion') - F('insurance_amount_paid'),
                ),
                default=Value(0),
                output_field=DecimalField(max_digits=14, decimal_places=2),
            )
        ),
    )

    status_breakdown = (
        queryset
        .values('payment_status')
        .annotate(count=Count('id'), total=Sum('total_amount'))
        .order_by('payment_status')
    )

    # ── Sorting ──────────────────────────────────────────────────────────────
    sort = request.GET.get('sort', '-created_at')
    allowed_sorts = {'-created_at', 'created_at', '-total_amount', 'total_amount'}
    if sort not in allowed_sorts:
        sort = '-created_at'
    queryset = queryset.order_by(sort)

    # ── Pagination ───────────────────────────────────────────────────────────
    paginator = Paginator(queryset, 25)
    page_obj = paginator.get_page(request.GET.get('page'))

    # Annotate each row with derived display values
    for billing in page_obj:
        billing.balance = billing.get_balance_due()
        billing.patient_balance = max(
            D(billing.patient_portion) - D(billing.patient_amount_paid), D('0.00')
        )
        billing.insurance_balance = max(
            D(billing.insurance_portion) - D(billing.insurance_amount_paid), D('0.00')
        )
        billing.is_overdue_flag = (
            billing.payment_status in ('UNPAID', 'PARTIAL')
            and (timezone.now().date() - billing.created_at.date()).days > 30
        )

    # Provider list for the filter dropdown
    insurance_providers = InsuranceProvider.objects.filter(
        vendor=vendor, is_active=True
    ).order_by('provider_type', 'name')

    context = {
        'billings':   page_obj,
        'page_obj':   page_obj,
        'paginator':  paginator,

        # Active filter values (passed back for template to repopulate inputs)
        'q':              q,
        'billing_type':   billing_type,
        'payment_status': payment_status,
        'date_from':      date_from_str,
        'date_to':        date_to_str,
        'provider_id':    provider_id,
        'sort':           sort,

        # Statistics
        'summary':          summary,
        'status_breakdown': status_breakdown,

        # Filter dropdown data
        'insurance_providers': insurance_providers,

        # Choices for billing type and status filter dropdowns
        'billing_type_choices':   BillingInformation.BILLING_TYPES,
        'payment_status_choices': BillingInformation.PAYMENT_STATUS,
    }

    return render(request, 'billing/billing/list.html', context)


# ─────────────────────
# Billing Create
# ──────────────────────────

@login_required
def billing_create_view(request, request_id):
    test_request = get_object_or_404(
        'labs.TestRequest',
        pk=request_id,
        vendor=request.user.vendor
    )

    # Billing must already exist
    billing = getattr(test_request, "billing_info", None)
    if not billing:
        messages.error(request, "Billing record not found.")
        return redirect('dashboard')

    if request.method == "POST":
        form = BillingInformationForm(request.POST, instance=billing)
        if form.is_valid():
            form.save()
            messages.success(request, "Billing updated successfully.")
            return redirect("billing:billing_detail", pk=billing.pk)
    else:
        form = BillingInformationForm(instance=billing)

    ctx = {
        "request_obj": test_request,
        "form": form,
    }
    return render(request, "billing/billing_create.html", ctx)


# ========================================
# 1. AUTHORIZE TO PROCEED (Emergency/VIP)
# ========================================
@login_required
@require_capability('can_authorize_billing')
def authorize_billing_view(request, pk):
    """
    Authorize sample collection to proceed WITHOUT payment.
    Debt remains tracked - use for emergencies, VIP, or pre-approved cases.
    
    Real-world scenarios:
    - Emergency patient needs immediate testing
    - VIP/staff with monthly billing arrangement
    - Insurance pre-authorization pending
    
    Status: UNPAID → AUTHORIZED (debt still exists)
    """
    billing = get_object_or_404(
        BillingInformation,
        pk=pk,
        vendor=request.user.vendor
    )

    # Already cleared - no action needed
    if billing.payment_status in ('PAID', 'AUTHORIZED', 'WAIVED'):
        messages.info(request, "Billing already cleared for sample collection.")
        return redirect('billing:billing_detail', pk=pk)

    if request.method == 'POST':
        reason = request.POST.get('reason', '').strip()
        if not reason:
            messages.error(request, "Authorization reason is required.")
            return redirect('billing:billing_detail', pk=pk)

        billing.payment_status = 'AUTHORIZED'
        billing.authorized_by = request.user
        billing.authorized_at = timezone.now()
        billing.authorization_reason = reason
        billing.save()

        messages.success(
            request,
            f"✅ Billing authorized. Sample collection can proceed. "
            f"Outstanding balance: ₦{billing.total_amount:,.2f} (tracked for later payment)"
        )

    return redirect('billing:billing_detail', pk=pk)


# ========================================
# 2. WAIVE PAYMENT (Write-off)
# ========================================
@login_required
@require_capability('can_waive_billing')
def waive_billing_view(request, pk):
    """
    Completely waive/write-off payment - debt is forgiven.
    
    Real-world scenarios:
    - Charity cases
    - Staff medical benefits
    - Goodwill gestures
    - Uncollectable debt write-offs
    
    Status: ANY → WAIVED (debt eliminated)
    """
    billing = get_object_or_404(
        BillingInformation,
        pk=pk,
        vendor=request.user.vendor
    )

    # Already waived
    if billing.payment_status == 'WAIVED':
        messages.info(request, "Billing already waived.")
        return redirect('billing:billing_detail', pk=pk)

    if request.method == 'POST':
        reason = request.POST.get('waiver_reason', '').strip()
        waiver_type = request.POST.get('waiver_type', 'full')  # full or partial
        
        if not reason:
            messages.error(request, "Waiver reason is required.")
            return redirect('billing:billing_detail', pk=pk)

        with transaction.atomic():
            if waiver_type == 'full':
                # Full waiver - entire amount forgiven
                billing.waiver_amount = billing.total_amount
                billing.payment_status = 'WAIVED'
            else:
                # Partial waiver - user specifies amount
                partial_amount = request.POST.get('partial_waiver_amount', '0')
                try:
                    partial_amount = D(partial_amount)
                    if partial_amount <= 0 or partial_amount > billing.total_amount:
                        raise ValueError("Invalid waiver amount")
                    
                    billing.waiver_amount = partial_amount
                    # Recalculate - if balance is now zero, mark as waived
                    billing.save()  # Triggers recalculation
                    
                    if billing.get_balance_due() <= D('0.00'):
                        billing.payment_status = 'WAIVED'
                    
                except (ValueError, TypeError):
                    messages.error(request, "Invalid waiver amount.")
                    return redirect('billing:billing_detail', pk=pk)

            billing.authorized_by = request.user
            billing.authorized_at = timezone.now()
            billing.authorization_reason = f"WAIVER: {reason}"
            billing.save()

            messages.success(
                request,
                f"✅ Payment waived (₦{billing.waiver_amount:,.2f}). "
                f"Sample collection can proceed."
            )

    return redirect('billing:billing_detail', pk=pk)


@login_required
@require_capability('can_receive_payment')
def confirm_payment_view(request, pk):
    billing = get_object_or_404(BillingInformation, pk=pk, vendor=request.user.vendor)

    if billing.payment_status == 'PAID':
        messages.info(request, "Billing already fully paid.")
        return redirect('billing:billing_detail', pk=pk)

    if request.method == 'POST':
        payment_method = request.POST.get('payment_method', '').strip()
        amount = D(request.POST.get('amount', '0').strip())
        
        # Validation
        balance_due = billing.get_balance_due()
        if amount > balance_due:
            amount = balance_due # Cap at balance due

        try:
            with transaction.atomic():
                # We only create the payment. 
                # The Payment.save() method we wrote earlier will 
                # automatically update billing.payment_status to PAID or PARTIAL.
                Payment.objects.create(
                    billing=billing,
                    amount=amount,
                    payment_method=payment_method,
                    transaction_reference=request.POST.get('transaction_reference', ''),
                    notes=request.POST.get('payment_notes', ''),
                    collected_by=request.user,
                )
            
            messages.success(request, f"✅ Payment of ₦{amount:,.2f} recorded.")
        except Exception as e:
            messages.error(request, f"Error: {str(e)}")
            
    return redirect('billing:billing_detail', pk=pk)


"""
billing/views.py — billing_detail_view

Changes in this refactor:
- corporate_client removed from select_related (model FK no longer exists)
- State flags now delegate to model properties (is_payment_cleared, is_fully_paid)
  rather than re-implementing the same logic in the view
- Patient portion / insurance portion added to context with clear labels
- HMO-specific context (copay rate, amounts still owed per party) added
- Payment methods sourced from Payment.PAYMENT_METHODS (single source of truth)
- AWAY_BACK sentinel replaced with a clean timezone-aware fallback
- Timeline waiver entry uses created_at as fallback when authorized_at is None
"""

import logging
# from datetime import datetime

# from django.contrib import messages
# from django.contrib.auth.decorators import login_required
# from django.core.exceptions import PermissionDenied
# from django.db.models import Sum
# from django.shortcuts import redirect, render
# from django.utils import timezone

# from ..models import BillingInformation, Payment
# from labs.utils import D  # your safe Decimal helper

logger = logging.getLogger(__name__)


@login_required
def billing_detail_view(request, pk):
    """
    Comprehensive billing record view.

    Financial summary surfaced:
    ┌────────────────────────────────────────────────────────┐
    │  subtotal          Sum of retail test prices           │
    │  discount          Negotiated rate discount applied    │
    │  tax               Tax on discounted amount            │
    │  total_amount      Final Contract Price                │
    │                                                        │
    │  patient_portion   What the patient pays at front desk │
    │  insurance_portion What the HMO/payer owes the lab     │
    │                                                        │
    │  patient_amount_paid   Collected so far from patient   │
    │  insurance_amount_paid Received so far from payer      │
    │  patient_balance_due   Still owed by the patient       │
    │  insurance_balance_due Still owed by the payer         │
    └────────────────────────────────────────────────────────┘
    """

    vendor = getattr(request.user, 'vendor', None)
    if vendor is None:
        raise PermissionDenied("Only vendor accounts can view billing records.")

    try:
        billing = (
            BillingInformation.objects
            .select_related(
                'request',
                'request__patient',
                'price_list',
                'insurance_provider',       # covers HMO, NHIS, Corporate, Staff
                'authorized_by',
            )
            .prefetch_related(
                'payments',
                'payments__collected_by',
                'request__requested_tests',
            )
            .get(pk=pk, vendor=vendor)
        )
    except BillingInformation.DoesNotExist:
        messages.error(request, "Billing record not found.")
        return redirect('billing:billing_list')

    test_request = billing.request
    provider = billing.insurance_provider  # may be None for CASH

    # ── State flags (delegate to model — don't re-implement here) ────────────
    #
    # billing.is_payment_cleared : patient has paid their portion (or it's Corporate/Staff)
    # billing.is_fully_paid()    : total paid >= total_amount
    #
    is_fully_paid   = billing.is_fully_paid()
    is_authorized   = billing.payment_status == 'AUTHORIZED'
    is_waived       = billing.payment_status == 'WAIVED'
    is_invoiced     = billing.payment_status == 'INVOICED'
    payment_cleared = billing.is_payment_cleared    # property on model
    is_blocked      = not payment_cleared

    sample_exists = (
        hasattr(test_request, 'sample') and test_request.sample is not None
    )
    can_collect_sample = payment_cleared and not sample_exists

    # ── Financial summary ────────────────────────────────────────────────────
    #
    # Total actually paid is derived from the Payment ledger (source of truth),
    # not from billing.patient_amount_paid alone, so we query it fresh.
    #
    total_paid_from_ledger = (
        billing.payments.aggregate(total=Sum('amount'))['total']
        or D('0.00')
    )

    # Per-party balances
    patient_balance_due   = max(D(billing.patient_portion)   - D(billing.patient_amount_paid),   D('0.00'))
    insurance_balance_due = max(D(billing.insurance_portion) - D(billing.insurance_amount_paid), D('0.00'))

    # Co-pay rate as a readable percentage (e.g. 0.6000 → "60%")
    copay_percentage = None
    hmo_percentage   = None
    if provider and billing.billing_type in ('HMO', 'NHIS', 'CORPORATE', 'STAFF'):
        rate = D(getattr(provider, 'patient_copay_percentage', 0))
        copay_percentage = round(rate * 100, 1)        # e.g. 60.0
        hmo_percentage   = round((1 - rate) * 100, 1)  # e.g. 40.0

    # ── Test breakdown ───────────────────────────────────────────────────────
    test_details = []
    for lab_test in test_request.requested_tests.all():
        if billing.price_list and callable(
            getattr(lab_test, 'get_price_from_price_list', None)
        ):
            try:
                price = D(lab_test.get_price_from_price_list(billing.price_list))
            except Exception:
                price = D(getattr(lab_test, 'price', 0))
        else:
            price = D(getattr(lab_test, 'price', 0))

        test_details.append({
            'test':  lab_test,
            'price': price,
        })

    # ── Timeline ─────────────────────────────────────────────────────────────
    _epoch = timezone.make_aware(datetime(2000, 1, 1))   # safe sort sentinel

    timeline = [
        {
            'type':        'billing',
            'date':        billing.created_at,
            'description': 'Billing record created',
            'amount':      billing.total_amount,
            'user':        None,
        }
    ]

    if is_authorized and billing.authorized_at:
        timeline.append({
            'type':        'authorization',
            'date':        billing.authorized_at,
            'description': 'Authorized to proceed',
            'reference':   billing.authorization_reason,
            'user':        billing.authorized_by,
        })

    if is_waived:
        timeline.append({
            'type':        'waiver',
            # authorized_at may be None if record was auto-waived
            'date':        billing.authorized_at or billing.created_at,
            'description': 'Payment waived',
            'amount':      billing.waiver_amount,
            'reference':   billing.authorization_reason,
            'user':        billing.authorized_by,
        })

    for payment in billing.payments.all():
        timeline.append({
            'type':        'payment',
            'date':        payment.payment_date,
            'description': f'{payment.get_payment_method_display()} payment received',
            'amount':      payment.amount,
            'reference':   payment.transaction_reference,
            'user':        payment.collected_by,
        })

    timeline.sort(key=lambda x: x['date'] or _epoch, reverse=True)

    # ── Context ──────────────────────────────────────────────────────────────
    context = {
        # Core objects
        'billing':      billing,
        'test_request': test_request,
        'provider':     provider,

        # ── State flags ──────────────────────────────────────────────────────
        'is_fully_paid':      is_fully_paid,
        'is_authorized':      is_authorized,
        'is_waived':          is_waived,
        'is_invoiced':        is_invoiced,
        'payment_cleared':    payment_cleared,
        'is_blocked':         is_blocked,
        'can_collect_sample': can_collect_sample,

        # ── Financial breakdown ───────────────────────────────────────────────
        # Pricing layers
        'subtotal':           billing.subtotal,
        'discount':           billing.discount,
        'tax':                billing.tax,
        'total_amount':       billing.total_amount,   # Final Contract Price

        # Co-pay split — the core of the HMO billing workflow
        'patient_portion':          billing.patient_portion,
        'insurance_portion':        billing.insurance_portion,

        # What has actually been collected / received
        'patient_amount_paid':      billing.patient_amount_paid,
        'insurance_amount_paid':    billing.insurance_amount_paid,

        # What is still outstanding per party
        'patient_balance_due':      patient_balance_due,
        'insurance_balance_due':    insurance_balance_due,

        # Total from the payment ledger (authoritative)
        'total_paid':               total_paid_from_ledger,
        'payment_count':            billing.payments.count(),

        'copay_percentage':         copay_percentage,   # None for CASH
        'hmo_percentage':           hmo_percentage,     # None for CASH

        # ── Tests & timeline ─────────────────────────────────────────────────
        'test_details': test_details,
        'timeline':     timeline,

        # ── Payment form options 
        'payment_methods': Payment.PAYMENT_METHODS,
    }

    return render(request, 'billing/billing/detail1.html', context)


@login_required
def billing_update_view(request, pk):
    """
    Update billing information.
    
    Features:
    - Edit billing type, discounts, waivers
    - Recalculate totals on save
    - Validation
    - Audit trail
    """
    
    # Validate vendor
    vendor = getattr(request.user, "vendor", None)
    if vendor is None:
        raise PermissionDenied("Only vendors can update billing records.")
    
    # Get billing record
    try:
        billing = BillingInformation.objects.select_related(
            'request', 'insurance_provider', 'corporate_client'
        ).get(pk=pk, vendor=vendor)
    except BillingInformation.DoesNotExist:
        messages.error(request, "Billing record not found.")
        return redirect('billing:billing_list')
    
    # Check if already paid
    if billing.payment_status == 'PAID':
        messages.warning(
            request,
            'This billing record is fully paid. Changes may affect financial records.'
        )
    
    if request.method == "POST":
        form = BillingInformationForm(request.POST, instance=billing, vendor=vendor)
        
        if form.is_valid():
            # Save with recalculation
            updated_billing = form.save()
            
            messages.success(
                request,
                f'Billing record for {billing.request.request_id} updated successfully. '
                f'New total: ₦{updated_billing.total_amount:,.2f}'
            )
            return redirect('billing:billing_detail', pk=updated_billing.pk)
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = BillingInformationForm(instance=billing, vendor=vendor)
    
    context = {
        "form": form,
        "billing": billing,
        "title": f"Edit Billing: {billing.request.request_id}",
        "submit_text": "Update Billing",
    }
    
    return render(request, "billing/billing/form.html", context)


@login_required
def billing_summary_view(request):
    """
    High-level billing summary and analytics.
    
    Features:
    - Revenue breakdown by type
    - Payment status distribution
    - Trend analysis
    - Top providers
    """
    
    vendor = getattr(request.user, "vendor", None)
    if vendor is None:
        raise PermissionDenied("Only vendors can view billing summary.")
    
    # Date range (default: current month)
    from datetime import datetime, timedelta
    today = timezone.now().date()
    first_day = today.replace(day=1)
    
    date_from = request.GET.get("date_from")
    if date_from:
        date_from = datetime.strptime(date_from, "%Y-%m-%d").date()
    else:
        date_from = first_day
    
    date_to = request.GET.get("date_to")
    if date_to:
        date_to = datetime.strptime(date_to, "%Y-%m-%d").date()
    else:
        date_to = today
    
    # Base queryset
    queryset = BillingInformation.objects.filter(
        vendor=vendor,
        created_at__date__range=[date_from, date_to]
    )
    
    # Revenue by billing type
    revenue_by_type = queryset.values('billing_type').annotate(
        count=Count('id'),
        total=Sum('total_amount'),
        avg=Avg('total_amount')
    ).order_by('-total')
    
    # Payment status distribution
    payment_distribution = queryset.values('payment_status').annotate(
        count=Count('id'),
        total=Sum('total_amount')
    )
    
    # Top insurance providers
    top_insurance = queryset.filter(
        billing_type='HMO'
    ).values(
        'insurance_provider__name'
    ).annotate(
        count=Count('id'),
        total=Sum('total_amount')
    ).order_by('-total')[:10]
    
    # Top corporate clients
    top_corporate = queryset.filter(
        billing_type='CORPORATE'
    ).values(
        'corporate_client__company_name'
    ).annotate(
        count=Count('id'),
        total=Sum('total_amount')
    ).order_by('-total')[:10]
    
    # Daily trend (last 30 days)
    daily_trend = []
    for i in range(30):
        day = today - timedelta(days=29-i)
        day_total = queryset.filter(
            created_at__date=day
        ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0')
        
        daily_trend.append({
            'date': day,
            'total': day_total
        })
    
    # Overall stats
    overall = queryset.aggregate(
        total_billings=Count('id'),
        total_revenue_sum=Sum('total_amount'),
        avg_billing=Avg('total_amount'),
        unpaid=Sum(
            Case(
                When(payment_status='UNPAID', then=F('total_amount')),
                default=0,
                output_field=DecimalField(max_digits=14, decimal_places=2)
            )
        ),
        paid=Sum(
            Case(
                When(payment_status='PAID', then='total_amount'),
                default=0,
                output_field=DecimalField()
            )
        ),
    )
    
    context = {
        "date_from": date_from,
        "date_to": date_to,
        "revenue_by_type": revenue_by_type,
        "payment_distribution": payment_distribution,
        "top_insurance": top_insurance,
        "top_corporate": top_corporate,
        "daily_trend": daily_trend,
        "overall": overall,
    }
    
    return render(request, "billing/billing/summary.html", context)


@login_required
def billing_bulk_action_view(request):
    """
    Perform bulk actions on billing records.
    
    Actions:
    - Mark as invoiced
    - Send reminders
    - Export to CSV
    """
    
    vendor = getattr(request.user, "vendor", None)
    if vendor is None:
        raise PermissionDenied("Only vendors can perform bulk actions.")
    
    if request.method == "POST":
        action = request.POST.get('action')
        billing_ids = request.POST.getlist('billing_ids')
        
        if not billing_ids:
            messages.warning(request, 'No billing records selected.')
            return redirect('billing:billing_list')
        
        billings = BillingInformation.objects.filter(
            vendor=vendor,
            id__in=billing_ids
        )
        
        if action == 'mark_invoiced':
            count = billings.update(payment_status='INVOICED')
            messages.success(request, f'{count} billing record(s) marked as invoiced.')
        
        elif action == 'export_csv':
            # Future: Generate CSV export
            messages.info(request, 'CSV export feature coming soon!')
        
        else:
            messages.warning(request, 'Invalid action selected.')
    
    return redirect('billing:billing_list')


# ==========================================
# BILLING RECALCULATE VIEW
# ==========================================

@login_required
def billing_recalculate_view(request, pk):
    """
    Force recalculation of billing totals.
    Useful when prices or discounts change.
    """
    
    vendor = getattr(request.user, "vendor", None)
    if vendor is None:
        raise PermissionDenied("Only vendors can recalculate billing.")
    
    try:
        billing = BillingInformation.objects.get(pk=pk, vendor=vendor)
    except BillingInformation.DoesNotExist:
        messages.error(request, "Billing record not found.")
        return redirect('billing:billing_list')
    
    if request.method == "POST":
        old_total = billing.total_amount
        
        # Force recalculation by saving
        billing.save()
        
        new_total = billing.total_amount
        
        if old_total != new_total:
            messages.success(
                request,
                f'Billing recalculated. Old total: ₦{old_total:,.2f}, '
                f'New total: ₦{new_total:,.2f}'
            )
        else:
            messages.info(request, 'Billing totals unchanged.')
        
        return redirect('billing:billing_detail', pk=pk)
    
    context = {
        "billing": billing,
    }
    
    return render(request, "billing/billing/recalculate_confirm.html", context)


# ==========================================
# BILLING PRINT/EXPORT VIEW
# ==========================================

@login_required
def billing_print_view(request, pk):
    """
    Generate printable billing statement.
    """
    
    vendor = getattr(request.user, "vendor", None)
    if vendor is None:
        raise PermissionDenied("Only vendors can print billing records.")
    
    try:
        billing = BillingInformation.objects.select_related(
            'request__patient',
            'insurance_provider',
            'corporate_client'
        ).prefetch_related(
            'request__test_assignments__test',
            'payments'
        ).get(pk=pk, vendor=vendor)
    except BillingInformation.DoesNotExist:
        messages.error(request, "Billing record not found.")
        return redirect('billing:billing_list')
    
    # Get test details
    test_details = []
    for assignment in billing.request.test_assignments.all():
        if billing.price_list:
            price = assignment.test.get_price_from_price_list(billing.price_list)
        else:
            price = assignment.test.price
        
        test_details.append({
            'test': assignment.test,
            'price': price,
        })
    
    context = {
        "billing": billing,
        "test_details": test_details,
        "balance_due": billing.get_balance_due(),
    }
    
    return render(request, "billing/billing/print.html", context)


# ==========================================
# PAYMENT VIEWS
# ==========================================

class PaymentCreateView(LoginRequiredMixin, View):
    """Record a new payment"""
    
    def post(self, request, billing_pk):
        billing = get_object_or_404(
            BillingInformation,
            pk=billing_pk,
            vendor=request.user.vendor
        )
        
        form = PaymentForm(request.POST, billing=billing)
        
        if form.is_valid():
            with transaction.atomic():
                payment = form.save(commit=False)
                payment.billing = billing
                payment.collected_by = request.user
                payment.save()
                
                messages.success(request, f'Payment of ₦{payment.amount:,.2f} recorded successfully.')
                return redirect('billing:billing_detail', pk=billing.pk)
        else:
            messages.error(request, 'Error recording payment. Please check the form.')
            return redirect('billing:billing_detail', pk=billing.pk)


# ==========================================
# REPORTING VIEWS
# ==========================================

class BillingReportView(LoginRequiredMixin, View):
    """Generate billing reports"""
    
    template_name = 'billing/reports.html'
    
    def get(self, request):
        vendor = request.user.vendor
        
        # Date range
        date_from = request.GET.get('date_from')
        date_to = request.GET.get('date_to')
        
        if not date_from:
            date_from = timezone.now().date().replace(day=1)
        else:
            date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
        
        if not date_to:
            date_to = timezone.now().date()
        else:
            date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
        
        # Revenue report
        revenue_data = BillingInformation.objects.filter(
            vendor=vendor,
            created_at__date__range=[date_from, date_to]
        ).values('billing_type').annotate(
            total_amount=Sum('total_amount'),
            count=Count('id')
        )
        
        # Payment status report
        payment_status_data = BillingInformation.objects.filter(
            vendor=vendor,
            created_at__date__range=[date_from, date_to]
        ).values('payment_status').annotate(
            total_amount=Sum('total_amount'),
            count=Count('id')
        )
        
        context = {
            'date_from': date_from,
            'date_to': date_to,
            'revenue_data': revenue_data,
            'payment_status_data': payment_status_data,
        }
        
        return render(request, self.template_name, context)
     
     


# # ========================================
# # 1. AUTHORIZE TO PROCEED (Emergency/VIP)
# # ========================================
# @login_required
# @require_capability('can_authorize_billing')
# def authorize_billing_view(request, pk):
#     """
#     Authorize sample collection to proceed WITHOUT payment.
#     Debt remains tracked - use for emergencies, VIP, or pre-approved cases.
    
#     Real-world scenarios:
#     - Emergency patient needs immediate testing
#     - VIP/staff with monthly billing arrangement
#     - Insurance pre-authorization pending
    
#     Status: UNPAID → AUTHORIZED (debt still exists)
#     """
#     billing = get_object_or_404(
#         BillingInformation,
#         pk=pk,
#         vendor=request.user.vendor
#     )

#     # Already cleared - no action needed
#     if billing.payment_status in ('PAID', 'AUTHORIZED', 'WAIVED'):
#         messages.info(request, "Billing already cleared for sample collection.")
#         return redirect('billing:billing_detail', pk=pk)

#     if request.method == 'POST':
#         reason = request.POST.get('reason', '').strip()
#         if not reason:
#             messages.error(request, "Authorization reason is required.")
#             return redirect('billing:billing_detail', pk=pk)

#         billing.payment_status = 'AUTHORIZED'
#         billing.authorized_by = request.user
#         billing.authorized_at = timezone.now()
#         billing.authorization_reason = reason
#         billing.save()

#         messages.success(
#             request,
#             f"✅ Billing authorized. Sample collection can proceed. "
#             f"Outstanding balance: ₦{billing.total_amount:,.2f} (tracked for later payment)"
#         )

#     return redirect('billing:billing_detail', pk=pk)


# # ========================================
# # 2. WAIVE PAYMENT (Write-off)
# # ========================================
# @login_required
# @require_capability('can_waive_billing')
# def waive_billing_view(request, pk):
#     """
#     Completely waive/write-off payment - debt is forgiven.
    
#     Real-world scenarios:
#     - Charity cases
#     - Staff medical benefits
#     - Goodwill gestures
#     - Uncollectable debt write-offs
    
#     Status: ANY → WAIVED (debt eliminated)
#     """
#     billing = get_object_or_404(
#         BillingInformation,
#         pk=pk,
#         vendor=request.user.vendor
#     )

#     # Already waived
#     if billing.payment_status == 'WAIVED':
#         messages.info(request, "Billing already waived.")
#         return redirect('billing:billing_detail', pk=pk)

#     if request.method == 'POST':
#         reason = request.POST.get('waiver_reason', '').strip()
#         waiver_type = request.POST.get('waiver_type', 'full')  # full or partial
        
#         if not reason:
#             messages.error(request, "Waiver reason is required.")
#             return redirect('billing:billing_detail', pk=pk)

#         with transaction.atomic():
#             if waiver_type == 'full':
#                 # Full waiver - entire amount forgiven
#                 billing.waiver_amount = billing.total_amount
#                 billing.payment_status = 'WAIVED'
#             else:
#                 # Partial waiver - user specifies amount
#                 partial_amount = request.POST.get('partial_waiver_amount', '0')
#                 try:
#                     partial_amount = D(partial_amount)
#                     if partial_amount <= 0 or partial_amount > billing.total_amount:
#                         raise ValueError("Invalid waiver amount")
                    
#                     billing.waiver_amount = partial_amount
#                     # Recalculate - if balance is now zero, mark as waived
#                     billing.save()  # Triggers recalculation
                    
#                     if billing.get_balance_due() <= D('0.00'):
#                         billing.payment_status = 'WAIVED'
                    
#                 except (ValueError, TypeError):
#                     messages.error(request, "Invalid waiver amount.")
#                     return redirect('billing:billing_detail', pk=pk)

#             billing.authorized_by = request.user
#             billing.authorized_at = timezone.now()
#             billing.authorization_reason = f"WAIVER: {reason}"
#             billing.save()

#             messages.success(
#                 request,
#                 f"✅ Payment waived (₦{billing.waiver_amount:,.2f}). "
#                 f"Sample collection can proceed."
#             )

#     return redirect('billing:billing_detail', pk=pk)


# # ========================================
# # 3. CONFIRM CASH/TRANSFER PAYMENT (Reception)
# # ========================================
# @login_required
# @require_capability('can_receive_payment')
# def confirm_payment_view(request, pk):
#     """
#     Reception confirms cash or bank transfer payment received.
#     Creates Payment record and updates billing status.
    
#     Real-world flow:
#     1. Patient pays cash or shows transfer proof
#     2. Receptionist confirms payment in system
#     3. Receipt printed
#     4. Sample collection proceeds
    
#     Status: UNPAID/PARTIAL → PAID (or PARTIAL if underpaid)
#     """
#     billing = get_object_or_404(
#         BillingInformation,
#         pk=pk,
#         vendor=request.user.vendor
#     )

#     # Already fully paid
#     if billing.payment_status == 'PAID':
#         messages.info(request, "Billing already fully paid.")
#         return redirect('billing:billing_detail', pk=pk)

#     if request.method == 'POST':
#         payment_method = request.POST.get('payment_method', '').strip()
#         amount_str = request.POST.get('amount', '0').strip()
#         transaction_ref = request.POST.get('transaction_reference', '').strip()
#         payment_notes = request.POST.get('payment_notes', '').strip()

#         # Validation
#         if not payment_method:
#             messages.error(request, "Payment method is required.")
#             return redirect('billing:billing_detail', pk=pk)

#         try:
#             amount = D(amount_str)
#             if amount <= D('0.00'):
#                 raise ValueError("Amount must be greater than zero")
#         except (ValueError, TypeError):
#             messages.error(request, "Invalid payment amount.")
#             return redirect('billing:billing_detail', pk=pk)

#         # Get current balance
#         balance_due = billing.get_balance_due()
        
#         if amount > balance_due:
#             messages.warning(
#                 request,
#                 f"Payment amount (₦{amount:,.2f}) exceeds balance due (₦{balance_due:,.2f}). "
#                 f"Accepting payment for full balance."
#             )
#             amount = balance_due

#         try:
#             with transaction.atomic():
#                 # Create Payment record
#                 payment = Payment.objects.create(
#                     vendor=request.user.vendor,
#                     billing=billing,
#                     amount=amount,
#                     payment_method=payment_method,
#                     transaction_reference=transaction_ref,
#                     payment_notes=payment_notes,
#                     received_by=request.user,
#                     payment_date=timezone.now(),
#                     status='completed'
#                 )

#                 # Update billing status
#                 new_balance = billing.get_balance_due()
                
#                 if new_balance <= D('0.00'):
#                     billing.payment_status = 'PAID'
#                     status_msg = "fully paid"
#                 elif billing.payment_status == 'UNPAID':
#                     billing.payment_status = 'PARTIAL'
#                     status_msg = f"partially paid (₦{new_balance:,.2f} remaining)"
#                 else:
#                     status_msg = f"payment recorded (₦{new_balance:,.2f} remaining)"

#                 billing.save()

#                 messages.success(
#                     request,
#                     f"✅ Payment of ₦{amount:,.2f} confirmed. "
#                     f"Billing is now {status_msg}. "
#                     f"Receipt: {payment.receipt_number}"
#                 )

#         except Exception as e:
#             messages.error(request, f"Error processing payment: {str(e)}")
#             return redirect('billing:billing_detail', pk=pk)

#     return redirect('billing:billing_detail', pk=pk)


# # ========================================
# # 4. BILLING DETAIL VIEW (Enhanced)
# # ========================================
# @login_required
# def billing_detail_view(request, pk):
#     """
#     Comprehensive billing record with all payment/authorization options.
#     """
#     vendor = getattr(request.user, "vendor", None)
#     if vendor is None:
#         from django.core.exceptions import PermissionDenied
#         raise PermissionDenied("Only vendors can view billing records.")

#     try:
#         billing = (
#             BillingInformation.objects
#             .select_related(
#                 'request',
#                 'request__patient',
#                 'price_list',
#                 'insurance_provider',
#                 'corporate_client',
#                 'authorized_by'
#             )
#             .prefetch_related(
#                 'payments',
#                 'request__requested_tests'
#             )
#             .get(pk=pk, vendor=vendor)
#         )
#     except BillingInformation.DoesNotExist:
#         messages.error(request, "Billing record not found.")
#         return redirect('billing:billing_list')

#     test_request = billing.request

#     # ========================================
#     # BILLING STATE FLAGS
#     # ========================================
#     is_fully_paid = billing.is_fully_paid()
#     is_authorized = billing.payment_status == 'AUTHORIZED'
#     is_waived = billing.payment_status == 'WAIVED'
#     is_blocked = billing.payment_status not in ('PAID', 'AUTHORIZED', 'WAIVED')
    
#     # Can proceed to sample collection?
#     can_collect_sample = not is_blocked

#     # ========================================
#     # PAYMENT SUMMARY
#     # ========================================
#     total_paid = (
#         billing.payments.aggregate(total=Sum('amount'))['total']
#         or D('0.00')
#     )
#     balance_due = billing.get_balance_due()
#     payment_count = billing.payments.count()

#     # ========================================
#     # TEST BREAKDOWN
#     # ========================================
#     test_details = []
#     for lab_test in test_request.requested_tests.all():
#         if billing.price_list:
#             try:
#                 price = lab_test.get_price_from_price_list(billing.price_list)
#             except Exception:
#                 price = lab_test.price
#         else:
#             price = lab_test.price

#         test_details.append({
#             'test': lab_test,
#             'price': price,
#         })

#     # # ========================================
#     # # SAMPLE STATUS
#     # # ========================================
#     # sample = getattr(test_request, 'sample', None)
#     # sample_collected = sample is not None

#     # ========================================
#     # TIMELINE
#     # ========================================
#     timeline = [{
#         'type': 'billing',
#         'date': billing.created_at,
#         'description': 'Billing record created',
#         'amount': billing.total_amount,
#         'user': None,
#     }]

#     if is_authorized and billing.authorized_at:
#         timeline.append({
#             'type': 'authorization',
#             'date': billing.authorized_at,
#             'description': f'Authorized to proceed',
#             'reference': billing.authorization_reason,
#             'user': billing.authorized_by,
#         })

#     if is_waived and billing.waiver_amount:
#         timeline.append({
#             'type': 'waiver',
#             'date': billing.authorized_at,
#             'description': f'Payment waived',
#             'amount': billing.waiver_amount,
#             'reference': billing.authorization_reason,
#             'user': billing.authorized_by,
#         })

#     for payment in billing.payments.all():
#         timeline.append({
#             'type': 'payment',
#             'date': payment.payment_date,
#             'description': f'{payment.get_payment_method_display()} payment',
#             'amount': payment.amount,
#             'reference': payment.transaction_reference or payment.receipt_number,
#             'user': payment.received_by,
#         })

#     timeline.sort(key=lambda x: x['date'], reverse=True)

#     # ========================================
#     # CONTEXT
#     # ========================================
#     context = {
#         "billing": billing,
#         "test_request": test_request,

#         # State flags
#         "is_fully_paid": is_fully_paid,
#         "is_authorized": is_authorized,
#         "is_waived": is_waived,
#         "is_blocked": is_blocked,
#         "can_collect_sample": can_collect_sample,
#         # "sample_collected": sample_collected,

#         # Financials
#         "balance_due": balance_due,
#         "total_paid": total_paid,
#         "payment_count": payment_count,

#         # # Permissions
#         # "can_authorize": can_authorize,
#         # "can_waive": can_waive,
#         # "can_receive_payment": can_receive_payment,

#         # Tests & Sample
#         "test_details": test_details,
#         # "sample": sample,

#         # UI
#         "timeline": timeline,
        
#         # Payment methods for form
#         "payment_methods": [
#             ('cash', 'Cash'),
#             ('bank_transfer', 'Bank Transfer'),
#             ('pos', 'POS/Card'),
#             ('cheque', 'Cheque'),
#             ('mobile_money', 'Mobile Money'),
#         ],
#     }

#     return render(request, "billing/billing/detail3.html", context)







# # ==========================================
# # DASHBOARD
# # ==========================================
# class BillingDashboardView(LoginRequiredMixin, View):
#     template_name = 'billing/dashboard.html'

#     def get(self, request):
#         vendor = request.user.vendor

#         # -----------------------------------
#         # DATE RANGE FILTER
#         # -----------------------------------
#         range_opt = request.GET.get("range", "this_month")
#         today = timezone.now().date()

#         if range_opt == "today":
#             start_date = today
#             end_date = today

#         elif range_opt == "this_week":
#             start_date = today - timedelta(days=today.weekday())  # Monday
#             end_date = today

#         elif range_opt == "last_month":
#             first_of_this_month = today.replace(day=1)
#             last_month_end = first_of_this_month - timedelta(days=1)
#             start_date = last_month_end.replace(day=1)
#             end_date = last_month_end

#         elif range_opt == "this_quarter":
#             quarter = (today.month - 1) // 3 + 1
#             start_month = 3 * quarter - 2
#             start_date = date(today.year, start_month, 1)
#             end_date = today

#         elif range_opt == "this_year":
#             start_date = date(today.year, 1, 1)
#             end_date = today

#         else:  # default: this month
#             start_date = today.replace(day=1)
#             end_date = today

#         # Base queryset for the selected range
#         billing_qs = BillingInformation.objects.filter(
#             vendor=vendor,
#             created_at__date__range=[start_date, end_date]
#         )

#         # -----------------------------------
#         # SUMMARY METRICS
#         # -----------------------------------
#         total_revenue = billing_qs.filter(
#             payment_status__in=['PAID', 'PARTIAL']
#         ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0')

#         outstanding_balance = billing_qs.filter(
#             payment_status__in=['UNPAID', 'PARTIAL', 'INVOICED']
#         ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0')

#         unpaid_invoices = Invoice.objects.filter(
#             vendor=vendor,
#             status__in=['SENT', 'OVERDUE']
#         ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0')

#         # -----------------------------------
#         # RECENT LIST
#         # -----------------------------------
#         recent_billings = billing_qs.select_related(
#             'request', 'insurance_provider', 'corporate_client'
#         ).order_by('-created_at')[:10]

#         # -----------------------------------
#         # BREAKDOWN DATA
#         # -----------------------------------
#         payment_breakdown = billing_qs.values('payment_status').annotate(
#             count=Count('id'),
#             total=Sum('total_amount')
#         )

#         billing_breakdown = billing_qs.values('billing_type').annotate(
#             count=Count('id'),
#             total=Sum('total_amount')
#         )

#         # -----------------------------------
#         # Context
#         # -----------------------------------
#         context = {
#             "range": range_opt,
#             "start_date": start_date,
#             "end_date": end_date,

#             "total_revenue": total_revenue,
#             "outstanding_balance": outstanding_balance,
#             "unpaid_invoices": unpaid_invoices,

#             "payment_breakdown": payment_breakdown,
#             "billing_breakdown": billing_breakdown,
#             "recent_billings": recent_billings,
#         }

#         return render(request, self.template_name, context)


# @login_required
# def billing_list_view(request):
#     """
#     Features:
#     - Full text search
#     - Billing type filter
#     - Payment status filter
#     - Date range filter
#     - Insurance/Corporate provider filter
#     - Sorting options
#     - Summary statistics
#     - Status breakdown
#     - Pagination
#     """
#     vendor = getattr(request.user, "vendor", None)
#     if vendor is None:
#         raise PermissionDenied("Only vendors can access billing records.")

#     queryset = BillingInformation.objects.filter(
#         vendor=vendor
#     ).select_related(
#         "request", "request__patient",
#         "price_list", "insurance_provider",
#         "corporate_client"
#     )

#     # ------------------------
#     # SEARCH
#     # ------------------------
#     q = request.GET.get("q")
#     if q:
#         queryset = queryset.filter(
#             Q(request__request_id__icontains=q) |
#             Q(request__patient__first_name__icontains=q) |
#             Q(request__patient__last_name__icontains=q) |
#             Q(policy_number__icontains=q) |
#             Q(employee_id__icontains=q)
#         )

#     # ------------------------
#     # FILTERS
#     # ------------------------
#     billing_type = request.GET.get("billing_type")
#     if billing_type:
#         queryset = queryset.filter(billing_type=billing_type)

#     payment_status = request.GET.get("payment_status")
#     if payment_status:
#         queryset = queryset.filter(payment_status=payment_status)

#     date_from = request.GET.get("date_from")
#     if date_from:
#         date_from_obj = datetime.strftime(date_from, "%Y-%m-%d").date()
#         queryset = queryset.filter(created_at__date__gte=date_from_obj)

#     date_to = request.GET.get("date_to")
#     if date_to:
#         date_to_obj = datetime.strftime(date_from, "%Y-%m-%d").date()
#         queryset = queryset.filter(created_at__date__lte=date_to_obj)

#     provider_id = request.GET.get("provider")
#     if provider_id:
#         queryset = queryset.filter(
#             Q(insurance_provider_id=provider_id) |
#             Q(corporate_client_id=provider_id)
#         )

#     # ------------------------
#     # SUMMARY STATISTICS
#     # ------------------------
#     summary = queryset.aggregate(
#         total_billings=Count("id"),
#         total_amount_sum=Sum("total_amount"),
#         unpaid_amount=Sum(
#             Case(
#                 When(payment_status="UNPAID", then=F("total_amount")),
#                 default=Value(0),
#                 output_field=DecimalField(max_digits=14, decimal_places=2)
#             )
#         ),
#         paid_amount=Sum(
#             Case(
#                 When(payment_status="PAID", then=F("total_amount")),
#                 default=Value(0),
#                 output_field=DecimalField(max_digits=14, decimal_places=2)
#             )
#         ),
#     )

#     # Breakdown by payment status
#     status_breakdown = queryset.values("payment_status").annotate(
#         count=Count("id"),
#         total=Sum("total_amount")   # still safe here
#     ).order_by("payment_status")

#     # ------------------------
#     # SORTING
#     # ------------------------
#     sort = request.GET.get("sort", "-created_at")
#     allowed_sorts = {
#         "-created_at", "created_at",
#         "-total_amount", "total_amount"
#     }
#     if sort in allowed_sorts:
#         queryset = queryset.order_by(sort)

#     # ------------------------
#     # PAGINATION
#     # ------------------------
#     paginator = Paginator(queryset, 25)
#     page_obj = paginator.get_page(request.GET.get("page"))

#     for billing in page_obj:
#         billing.balance = billing.get_balance_due()
#         billing.is_overdue = (
#             billing.payment_status in ["UNPAID", "PARTIAL"] and
#             (timezone.now().date() - billing.created_at.date()).days > 30
#         )

#     insurance_providers = InsuranceProvider.objects.filter(
#         vendor=vendor, is_active=True
#     )
#     corporate_clients = CorporateClient.objects.filter(
#         vendor=vendor, is_active=True
#     )

#     context = {
#         "billings": page_obj,
#         "page_obj": page_obj,
#         "paginator": paginator,
#         "q": q or "",
#         "billing_type": billing_type or "",
#         "payment_status": payment_status or "",
#         "date_from": date_from or "",
#         "date_to": date_to or "",
#         "provider_id": provider_id or "",
#         "sort": sort,
#         "summary": summary,
#         "status_breakdown": status_breakdown,
#         "insurance_providers": insurance_providers,
#         "corporate_clients": corporate_clients,
#     }

#     return render(request, "billing/billing/list.html", context)



# ========================================
# 4. BILLING DETAIL VIEW (Enhanced)
# ========================================
# @login_required
# def billing_detail_view(request, pk):
#     """
#     Comprehensive billing record with all payment/authorization options.
#     """
#     vendor = getattr(request.user, "vendor", None)
#     if vendor is None:
#         from django.core.exceptions import PermissionDenied
#         raise PermissionDenied("Only vendors can view billing records.")

#     try:
#         billing = (
#             BillingInformation.objects
#             .select_related(
#                 'request',
#                 'request__patient',
#                 'price_list',
#                 'insurance_provider',
#                 'corporate_client',
#                 'authorized_by'
#             )
#             .prefetch_related(
#                 'payments',
#                 'request__requested_tests'
#             )
#             .get(pk=pk, vendor=vendor)
#         )
#     except BillingInformation.DoesNotExist:
#         messages.error(request, "Billing record not found.")
#         return redirect('billing:billing_list')

#     test_request = billing.request

#     # ========================================
#     # BILLING STATE FLAGS
#     # ========================================
#     is_fully_paid = billing.payment_status == 'PAID'
#     is_authorized = billing.payment_status == 'AUTHORIZED'
#     is_waived = billing.payment_status == 'WAIVED'
    
#     # Payment is cleared if: PAID, AUTHORIZED, or WAIVED
#     payment_cleared = billing.payment_status in ['PAID', 'AUTHORIZED', 'WAIVED']
    
#     # Blocked means payment not cleared
#     is_blocked = not payment_cleared
    
#     # Can proceed to sample collection?
#     can_collect_sample = payment_cleared

#     # ========================================
#     # PAYMENT SUMMARY
#     # ========================================
#     total_paid = (
#         billing.payments.aggregate(total=Sum('amount'))['total']
#         or D('0.00')
#     )
#     balance_due = billing.get_balance_due()
#     payment_count = billing.payments.count()

#     # ========================================
#     # TEST BREAKDOWN
#     # ========================================
#     test_details = []
#     for lab_test in test_request.requested_tests.all():
#         if billing.price_list:
#             try:
#                 price = lab_test.get_price_from_price_list(billing.price_list)
#             except Exception:
#                 price = lab_test.price
#         else:
#             price = lab_test.price

#         test_details.append({
#             'test': lab_test,
#             'price': price,
#         })

#     # ========================================
#     # SAMPLE STATUS
#     # ========================================
#     sample_exists = hasattr(test_request, 'sample') and test_request.sample is not None

#     # ========================================
#     # TIMELINE
#     # ========================================
#     timeline = [{
#         'type': 'billing',
#         'date': billing.created_at,
#         'description': 'Billing record created',
#         'amount': billing.total_amount,
#         'user': None,
#     }]

#     if is_authorized and billing.authorized_at:
#         timeline.append({
#             'type': 'authorization',
#             'date': billing.authorized_at,
#             'description': f'Authorized to proceed',
#             'reference': billing.authorization_reason,
#             'user': billing.authorized_by,
#         })

#     if is_waived and billing.waiver_amount:
#         timeline.append({
#             'type': 'waiver',
#             'date': billing.authorized_at,
#             'description': f'Payment waived',
#             'amount': billing.waiver_amount,
#             'reference': billing.authorization_reason,
#             'user': billing.authorized_by,
#         })

#     for payment in billing.payments.all():
#         timeline.append({
#             'type': 'payment',
#             'date': payment.payment_date,
#             'description': f'{payment.get_payment_method_display()} payment',
#             'amount': payment.amount,
#             'reference': payment.transaction_reference,
#             'user': payment.collected_by,
#         })


#     # Define a fallback date (e.g., the beginning of time)
#     AWAY_BACK = timezone.make_aware(datetime.min)

#     timeline.sort(
#         key=lambda x: x['date'] if x['date'] else AWAY_BACK, 
#         reverse=True
#     )
#     # timeline.sort(key=lambda x: x['date'], reverse=True)

#     # ========================================
#     # CONTEXT
#     # ========================================
#     context = {
#         "billing": billing,
#         "test_request": test_request,

#         # State flags
#         "is_fully_paid": is_fully_paid,
#         "is_authorized": is_authorized,
#         "is_waived": is_waived,
#         "is_blocked": is_blocked,
#         "payment_cleared":payment_cleared,
        
#         "can_collect_sample": payment_cleared and not sample_exists,

#         # Financials
#         "balance_due": balance_due,
#         "total_paid": total_paid,
#         "payment_count": payment_count,

#         # Tests & Sample
#         "test_details": test_details,
#         # "sample": sample,

#         # UI
#         "timeline": timeline,
        
#         # Payment methods for form
#         "payment_methods": [
#             ('cash', 'Cash'),
#             ('bank_transfer', 'Bank Transfer'),
#             ('pos', 'POS/Card'),
#             ('cheque', 'Cheque'),
#             ('mobile_money', 'Mobile Money'),
#         ],
#     }

#     return render(request, "billing/billing/detail.html", context)