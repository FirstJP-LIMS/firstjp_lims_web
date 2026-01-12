from decimal import Decimal
from datetime import datetime, timedelta, date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import models, transaction
from django.db.models import Q, Sum, Count, Avg, Case, When, DecimalField, F, Value
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy, reverse
from django.utils import timezone
from django.views.generic import (
    ListView, DetailView, CreateView, UpdateView, DeleteView, View
)

from decimal import Decimal
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import models, transaction
from django.db.models import Q, Sum, Count, Avg, F, Case, When, DecimalField, Value
    
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from datetime import datetime
from ..models import BillingInformation, Payment, InsuranceProvider, CorporateClient, Invoice
from ..forms import BillingInformationForm, BillingFilterForm, PaymentForm


# ==========================================
# DASHBOARD
# ==========================================
class BillingDashboardView(LoginRequiredMixin, View):
    template_name = 'billing/dashboard.html'

    def get(self, request):
        vendor = request.user.vendor

        # -----------------------------------
        # DATE RANGE FILTER
        # -----------------------------------
        range_opt = request.GET.get("range", "this_month")
        today = timezone.now().date()

        if range_opt == "today":
            start_date = today
            end_date = today

        elif range_opt == "this_week":
            start_date = today - timedelta(days=today.weekday())  # Monday
            end_date = today

        elif range_opt == "last_month":
            first_of_this_month = today.replace(day=1)
            last_month_end = first_of_this_month - timedelta(days=1)
            start_date = last_month_end.replace(day=1)
            end_date = last_month_end

        elif range_opt == "this_quarter":
            quarter = (today.month - 1) // 3 + 1
            start_month = 3 * quarter - 2
            start_date = date(today.year, start_month, 1)
            end_date = today

        elif range_opt == "this_year":
            start_date = date(today.year, 1, 1)
            end_date = today

        else:  # default: this month
            start_date = today.replace(day=1)
            end_date = today

        # Base queryset for the selected range
        billing_qs = BillingInformation.objects.filter(
            vendor=vendor,
            created_at__date__range=[start_date, end_date]
        )

        # -----------------------------------
        # SUMMARY METRICS
        # -----------------------------------
        total_revenue = billing_qs.filter(
            payment_status__in=['PAID', 'PARTIAL']
        ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0')

        outstanding_balance = billing_qs.filter(
            payment_status__in=['UNPAID', 'PARTIAL', 'INVOICED']
        ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0')

        unpaid_invoices = Invoice.objects.filter(
            vendor=vendor,
            status__in=['SENT', 'OVERDUE']
        ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0')

        # -----------------------------------
        # RECENT LIST
        # -----------------------------------
        recent_billings = billing_qs.select_related(
            'request', 'insurance_provider', 'corporate_client'
        ).order_by('-created_at')[:10]

        # -----------------------------------
        # BREAKDOWN DATA
        # -----------------------------------
        payment_breakdown = billing_qs.values('payment_status').annotate(
            count=Count('id'),
            total=Sum('total_amount')
        )

        billing_breakdown = billing_qs.values('billing_type').annotate(
            count=Count('id'),
            total=Sum('total_amount')
        )

        # -----------------------------------
        # Context
        # -----------------------------------
        context = {
            "range": range_opt,
            "start_date": start_date,
            "end_date": end_date,

            "total_revenue": total_revenue,
            "outstanding_balance": outstanding_balance,
            "unpaid_invoices": unpaid_invoices,

            "payment_breakdown": payment_breakdown,
            "billing_breakdown": billing_breakdown,
            "recent_billings": recent_billings,
        }

        return render(request, self.template_name, context)



@login_required
def billing_list_view(request):
    """
    Features:
    - Full text search
    - Billing type filter
    - Payment status filter
    - Date range filter
    - Insurance/Corporate provider filter
    - Sorting options
    - Summary statistics
    - Status breakdown
    - Pagination
    """
    vendor = getattr(request.user, "vendor", None)
    if vendor is None:
        raise PermissionDenied("Only vendors can access billing records.")

    queryset = BillingInformation.objects.filter(
        vendor=vendor
    ).select_related(
        "request", "request__patient",
        "price_list", "insurance_provider",
        "corporate_client"
    )

    # ------------------------
    # SEARCH
    # ------------------------
    q = request.GET.get("q")
    if q:
        queryset = queryset.filter(
            Q(request__request_id__icontains=q) |
            Q(request__patient__first_name__icontains=q) |
            Q(request__patient__last_name__icontains=q) |
            Q(policy_number__icontains=q) |
            Q(employee_id__icontains=q)
        )

    # ------------------------
    # FILTERS
    # ------------------------
    billing_type = request.GET.get("billing_type")
    if billing_type:
        queryset = queryset.filter(billing_type=billing_type)

    payment_status = request.GET.get("payment_status")
    if payment_status:
        queryset = queryset.filter(payment_status=payment_status)

    date_from = request.GET.get("date_from")
    if date_from:
        date_from_obj = datetime.strftime(date_from, "%Y-%m-%d").date()
        queryset = queryset.filter(created_at__date__gte=date_from_oj)

    date_to = request.GET.get("date_to")
    if date_to:
        date_to_obj = datetime.strftime(date_from, "%Y-%m-%d").date()
        queryset = queryset.filter(created_at__date__lte=date_to_obj)

    provider_id = request.GET.get("provider")
    if provider_id:
        queryset = queryset.filter(
            Q(insurance_provider_id=provider_id) |
            Q(corporate_client_id=provider_id)
        )

    # ------------------------
    # SUMMARY STATISTICS
    # ------------------------
    summary = queryset.aggregate(
        total_billings=Count("id"),
        total_amount_sum=Sum("total_amount"),
        unpaid_amount=Sum(
            Case(
                When(payment_status="UNPAID", then=F("total_amount")),
                default=Value(0),
                output_field=DecimalField(max_digits=14, decimal_places=2)
            )
        ),
        paid_amount=Sum(
            Case(
                When(payment_status="PAID", then=F("total_amount")),
                default=Value(0),
                output_field=DecimalField(max_digits=14, decimal_places=2)
            )
        ),
    )

    # Breakdown by payment status
    status_breakdown = queryset.values("payment_status").annotate(
        count=Count("id"),
        total=Sum("total_amount")   # still safe here
    ).order_by("payment_status")

    # ------------------------
    # SORTING
    # ------------------------
    sort = request.GET.get("sort", "-created_at")
    allowed_sorts = {
        "-created_at", "created_at",
        "-total_amount", "total_amount"
    }
    if sort in allowed_sorts:
        queryset = queryset.order_by(sort)

    # ------------------------
    # PAGINATION
    # ------------------------
    paginator = Paginator(queryset, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    for billing in page_obj:
        billing.balance = billing.get_balance_due()
        billing.is_overdue = (
            billing.payment_status in ["UNPAID", "PARTIAL"] and
            (timezone.now().date() - billing.created_at.date()).days > 30
        )

    insurance_providers = InsuranceProvider.objects.filter(
        vendor=vendor, is_active=True
    )
    corporate_clients = CorporateClient.objects.filter(
        vendor=vendor, is_active=True
    )

    context = {
        "billings": page_obj,
        "page_obj": page_obj,
        "paginator": paginator,
        "q": q or "",
        "billing_type": billing_type or "",
        "payment_status": payment_status or "",
        "date_from": date_from or "",
        "date_to": date_to or "",
        "provider_id": provider_id or "",
        "sort": sort,
        "summary": summary,
        "status_breakdown": status_breakdown,
        "insurance_providers": insurance_providers,
        "corporate_clients": corporate_clients,
    }

    return render(request, "billing/billing/list.html", context)


@login_required
def billing_create_view(request, request_id):
    """
    Create billing information for a TestRequest.
    Ensures:
    - One billing record per request (OneToOneField)
    - Auto-calculation from model.save()
    - Vendor scoping for multi-tenancy
    """
    test_request = get_object_or_404(
        'labs.TestRequest',
        pk=request_id,
        vendor=request.user.vendor  # vendor scoping
    )

    # If a billing record already exists → redirect to update
    if hasattr(test_request, "billing_info"):
        return redirect("billing:billing_update", billing_id=test_request.billing_info.pk)

    if request.method == "POST":
        form = BillingInformationForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                billing = form.save(commit=False)
                billing.vendor = request.user.vendor
                billing.request = test_request
                billing.save()  # auto-calculation occurs here
                messages.success(request, "Billing has been created successfully.")
                return redirect("billing:billing_detail", billing_id=billing.pk)
    else:
        # Pre-fill price list based on billing type
        initial = {}
        form = BillingInformationForm(initial=initial)

    ctx = {
        "request_obj": test_request,
        "form": form,
    }
    return render(request, "billing/billing_create.html", ctx)


@login_required
def billing_detail_view(request, pk):
    """
    View comprehensive billing record details.
    
    Features:
    - Full billing breakdown
    - Test assignments list
    - Payment history
    - Balance calculation
    - Payment form
    - Receipt generation
    """
    
    # Validate vendor
    vendor = getattr(request.user, "vendor", None)
    if vendor is None:
        raise PermissionDenied("Only vendors can view billing records.")
    
    # Get billing record
    try:
        billing = BillingInformation.objects.select_related(
            'request',
            'request__patient',
            'price_list',
            'insurance_provider',
            'corporate_client'
        ).prefetch_related(
            'payments',
            'request__assignments',
            'request__assignments__lab_test'
        ).get(pk=pk, vendor=vendor)
    except BillingInformation.DoesNotExist:
        messages.error(request, "Billing record not found.")
        return redirect('billing:billing_list')
    
    # Calculate balance
    balance_due = billing.get_balance_due()
    is_fully_paid = billing.is_fully_paid()
    
    # Payment summary
    total_paid = billing.payments.aggregate(total=Sum('amount'))['total'] or Decimal('0')
    payment_count = billing.payments.count()
    
    # Test breakdown
    test_assignments = billing.request.assignments.all()
    
    # Calculate individual test costs
    test_details = []
    for assignment in test_assignments:
        if billing.price_list:
            price = assignment.test.get_price_from_price_list(billing.price_list)
        else:
            price = assignment.lab_test.price
        
        test_details.append({
            'test': assignment.lab_test,
            'price': price,
        })
    
    # Payment form
    payment_form = PaymentForm(billing=billing) if not is_fully_paid else None
    
    # Timeline events (billing + payments)
    timeline = []
    
    # Add billing creation
    timeline.append({
        'type': 'billing',
        'date': billing.created_at,
        'description': 'Billing record created',
        'amount': billing.total_amount,
    })
    
    # Add payments
    for payment in billing.payments.all():
        timeline.append({
            'type': 'payment',
            'date': payment.payment_date,
            'description': f'Payment received ({payment.get_payment_method_display()})',
            'amount': payment.amount,
            'reference': payment.transaction_reference,
        })
    
    # Sort timeline by date
    timeline.sort(key=lambda x: x['date'], reverse=True)
    
    context = {
        "billing": billing,
        "balance_due": balance_due,
        "is_fully_paid": is_fully_paid,
        "total_paid": total_paid,
        "payment_count": payment_count,
        "test_details": test_details,
        "payment_form": payment_form,
        "timeline": timeline,
    }
    
    return render(request, "billing/billing/detail.html", context)


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
     
     