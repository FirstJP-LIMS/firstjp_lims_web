from decimal import Decimal
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import models, transaction
from django.db.models import Q, Sum, Count, Avg, Case, When, DecimalField, F, Value
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from .models import BillingInformation, Payment, InsuranceProvider, CorporateClient
from .forms import BillingInformationForm, BillingFilterForm, PaymentForm


# ==========================================
# BILLING LIST VIEW
# ==========================================

@login_required
def billing_list_view(request):
    """
    List all billing records with advanced filtering and search.
    
    Features:
    - Search by request ID, patient name
    - Filter by billing type, payment status, date range
    - Quick stats summary
    - Export options
    - Bulk actions
    """
    
    # Validate vendor
    vendor = getattr(request.user, "vendor", None)
    if vendor is None:
        raise PermissionDenied("Only vendors can access billing records.")
    
    # Base queryset
    queryset = BillingInformation.objects.filter(
        vendor=vendor
    ).select_related(
        'request',
        'request__patient',
        'price_list',
        'insurance_provider',
        'corporate_client'
    ).order_by('-created_at')
    
    # Search
    q = request.GET.get("q")
    if q:
        queryset = queryset.filter(
            Q(request__request_id__icontains=q) |
            Q(request__patient__first_name__icontains=q) |
            Q(request__patient__last_name__icontains=q) |
            Q(policy_number__icontains=q) |
            Q(employee_id__icontains=q)
        )
    
    # Filters
    billing_type = request.GET.get("billing_type")
    if billing_type:
        queryset = queryset.filter(billing_type=billing_type)
    
    payment_status = request.GET.get("payment_status")
    if payment_status:
        queryset = queryset.filter(payment_status=payment_status)
    
    # Date range
    date_from = request.GET.get("date_from")
    if date_from:
        from datetime import datetime
        date_from_obj = datetime.strptime(date_from, "%Y-%m-%d").date()
        queryset = queryset.filter(created_at__date__gte =date_from_obj)
    
    date_to = request.GET.get("date_to")
    if date_to:
        from datetime import datetime
        date_to_obj = datetime.strptime(date_to, "%Y-%m-%d").date()
        queryset = queryset.filter(created_at__date__lte=date_to_obj)
    
    # Provider filter
    provider_id = request.GET.get("provider")
    if provider_id:
        queryset = queryset.filter(
            Q(insurance_provider_id=provider_id) |
            Q(corporate_client_id=provider_id)
        )
    
    # Sort
    sort = request.GET.get("sort", "-created_at")
    valid_sorts = ['-created_at', 'created_at', '-total_amount', 'total_amount']
    if sort in valid_sorts:
        queryset = queryset.order_by(sort)
    
    # Pagination
    paginator = Paginator(queryset, 25)
    page_obj = paginator.get_page(request.GET.get("page"))
    
    # Calculate stats for display
    for billing in page_obj:
        billing.balance = billing.get_balance_due()
        billing.is_overdue = (
            billing.payment_status in ['UNPAID', 'PARTIAL'] and
            (timezone.now().date() - billing.created_at.date()).days > 30
        )
    
    # Summary statistics - use a CLONE of queryset
    from django.db.models import Case, When, DecimalField, Value
    
    summary_qs = queryset.all()  # Clone the queryset
    summary = summary_qs.aggregate(
        total_billings=Count('id'),
        total_amount=Sum('total_amount'),
        unpaid_amount=Sum(
            Case(
                When(payment_status='UNPAID', then=F('total_amount')),
                default=Value(0),
                output_field=DecimalField(max_digits=14, decimal_places=2)
            )
        ),
        paid_amount=Sum(
            Case(
                When(payment_status='PAID', then=F('total_amount')),
                default=Value(0),
                output_field=DecimalField(max_digits=14, decimal_places=2)
            )
        ),
    )
    
    # Status breakdown - use ANOTHER clone
    status_qs = queryset.all()  # Another clone
    status_breakdown = status_qs.values('payment_status').annotate(
        count=Count('id'),
        total=Sum('total_amount')
    ).order_by('payment_status')
    
    # Get providers for filter dropdown
    insurance_providers = InsuranceProvider.objects.filter(
        vendor=vendor, is_active=True
    ).order_by('name')
    
    corporate_clients = CorporateClient.objects.filter(
        vendor=vendor, is_active=True
    ).order_by('company_name')
    
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


# ==========================================
# BILLING DETAIL VIEW
# ==========================================

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
            'request__test_assignments',
            'request__test_assignments__test'
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
    test_assignments = billing.request.test_assignments.all()
    
    # Calculate individual test costs
    test_details = []
    for assignment in test_assignments:
        if billing.price_list:
            price = assignment.test.get_price_from_price_list(billing.price_list)
        else:
            price = assignment.test.price
        
        test_details.append({
            'test': assignment.test,
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


# ==========================================
# BILLING UPDATE VIEW
# ==========================================

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


# ==========================================
# BILLING SUMMARY VIEW
# ==========================================

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
        total_revenue=Sum('total_amount'),
        avg_billing=Avg('total_amount'),
        unpaid=Sum(
            Case(
                When(payment_status='UNPAID', then='total_amount'),
                default=0,
                output_field=DecimalField()
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


# ==========================================
# BULK BILLING ACTIONS
# ==========================================

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