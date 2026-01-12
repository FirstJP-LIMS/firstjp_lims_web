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

from ..models import (
    PriceList, TestPrice, InsuranceProvider, CorporateClient,
    BillingInformation, Payment, Invoice, InvoicePayment, D
)

from ..forms import (
    PriceListForm, TestPriceForm, InsuranceProviderForm, CorporateClientForm,
    BillingInformationForm, PaymentForm, InvoiceForm, InvoicePaymentForm,
    BillingFilterForm, InvoiceFilterForm
)

from ..utils import generate_invoice_pdf, generate_receipt_pdf


# ==========================================
# INSURANCE PROVIDER
# ==========================================

@login_required
def insurance_list_view(request):
    """
    List all insurance/HMO providers with filters and search.
    
    Features:
    - Search by name, code, contact person
    - Filter by active status
    - Sort by outstanding balance
    - Show credit limit warnings
    - Pagination
    """
    
    # Validate vendor
    vendor = getattr(request.user, "vendor", None)
    if vendor is None:
        raise PermissionDenied("Only vendors can access insurance providers.")
    
    # Base queryset
    queryset = InsuranceProvider.objects.filter(vendor=vendor).select_related('price_list')
    
    # Search
    q = request.GET.get("q")
    if q:
        queryset = queryset.filter(
            Q(name__icontains=q) |
            Q(code__icontains=q) |
            Q(contact_person__icontains=q) |
            Q(email__icontains=q)
        )
    
    # Filter by active status
    is_active = request.GET.get("active")
    if is_active == "yes":
        queryset = queryset.filter(is_active=True)
    elif is_active == "no":
        queryset = queryset.filter(is_active=False)
    
    # Filter by pre-auth requirement
    requires_preauth = request.GET.get("preauth")
    if requires_preauth == "yes":
        queryset = queryset.filter(requires_preauth=True)
    elif requires_preauth == "no":
        queryset = queryset.filter(requires_preauth=False)
    
    # Sort options
    sort = request.GET.get("sort", "name")
    if sort == "name":
        queryset = queryset.order_by("name")
    elif sort == "outstanding":
        # This would need annotation - simplified for now
        queryset = queryset.order_by("name")
    elif sort == "recent":
        queryset = queryset.order_by("-created_at")
    
    # Pagination
    paginator = Paginator(queryset, 20)
    page_obj = paginator.get_page(request.GET.get("page"))
    
    # Calculate stats for each provider
    for provider in page_obj:
        provider.outstanding = provider.get_outstanding_balance()
        provider.over_limit = provider.is_over_credit_limit()
        provider.invoice_count = provider.invoices.filter(
            status__in=['SENT', 'PARTIAL', 'OVERDUE']
        ).count()
    
    # Summary statistics
    total_providers = queryset.count()
    active_count = queryset.filter(is_active=True).count()
    
    context = {
        "providers": page_obj,
        "page_obj": page_obj,
        "paginator": paginator,
        "q": q or "",
        "is_active": is_active or "",
        "requires_preauth": requires_preauth or "",
        "sort": sort,
        "total_providers": total_providers,
        "active_count": active_count,
    }
    
    return render(request, "billing/insurance/list.html", context)


@login_required
def insurance_detail_view(request, pk):
    """
    View insurance provider details with financial summary.
    
    Features:
    - Outstanding balance calculation
    - Credit limit status
    - Recent invoices with pagination
    - Recent billing records
    - Payment history summary
    - Visual indicators for status
    """
    
    # Validate vendor
    vendor = getattr(request.user, "vendor", None)
    if vendor is None:
        raise PermissionDenied("Only vendors can view insurance providers.")
    
    # Get provider
    try:
        provider = InsuranceProvider.objects.select_related('price_list').get(
            pk=pk,
            vendor=vendor
        )
    except InsuranceProvider.DoesNotExist:
        messages.error(request, "Insurance provider not found.")
        return redirect('billing:insurance_list')
    
    # Financial summary
    outstanding_balance = provider.get_outstanding_balance()
    is_over_limit = provider.is_over_credit_limit()
    credit_available = provider.credit_limit - outstanding_balance
    
    # Invoices
    invoices = provider.invoices.order_by('-invoice_date')
    
    # Filter invoices by status if requested
    invoice_status = request.GET.get("invoice_status")
    if invoice_status:
        invoices = invoices.filter(status=invoice_status)
    
    # Pagination for invoices
    invoice_paginator = Paginator(invoices, 10)
    invoice_page_obj = invoice_paginator.get_page(request.GET.get("invoice_page"))
    
    # Recent billing records
    recent_billings = BillingInformation.objects.filter(
        vendor=vendor,
        insurance_provider=provider
    ).select_related('request').order_by('-created_at')[:10]
    
    # Statistics
    invoice_stats = provider.invoices.aggregate(
        total_invoices=Count('id'),
        total_amount=Sum('total_amount'),
        paid_amount=Sum('amount_paid'),
        unpaid_count=Count('id', filter=Q(status__in=['SENT', 'OVERDUE', 'PARTIAL']))
    )
    
    billing_stats = BillingInformation.objects.filter(
        vendor=vendor,
        insurance_provider=provider
    ).aggregate(
        total_billings=Count('id'),
        total_amount=Sum('total_amount'),
        insurance_portion=Sum('insurance_portion')
    )
    
    context = {
        "provider": provider,
        "outstanding_balance": outstanding_balance,
        "is_over_limit": is_over_limit,
        "credit_available": credit_available,
        "invoices": invoice_page_obj,
        "invoice_page_obj": invoice_page_obj,
        "invoice_paginator": invoice_paginator,
        "recent_billings": recent_billings,
        "invoice_stats": invoice_stats,
        "billing_stats": billing_stats,
        "invoice_status_filter": invoice_status or "",
    }
    
    return render(request, "billing/insurance/detail.html", context)


@login_required
def insurance_create_view(request):
    """
    Create a new insurance/HMO provider.
    
    Features:
    - Vendor auto-assignment
    - Price list selection (vendor-specific)
    - Form validation
    - Duplicate code checking
    """
    
    # Validate vendor
    vendor = getattr(request.user, "vendor", None)
    if vendor is None:
        raise PermissionDenied("Only vendors can create insurance providers.")
    
    if request.method == "POST":
        form = InsuranceProviderForm(request.POST, vendor=vendor)
        
        if form.is_valid():
            # Check for duplicate code
            code = form.cleaned_data['code']
            if InsuranceProvider.objects.filter(vendor=vendor, code=code).exists():
                messages.error(
                    request,
                    f'Insurance provider with code "{code}" already exists.'
                )
            else:
                provider = form.save(commit=False)
                provider.vendor = vendor
                provider.save()
                
                messages.success(
                    request,
                    f'Insurance provider "{provider.name}" created successfully.'
                )
                return redirect('billing:insurance_detail', pk=provider.pk)
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = InsuranceProviderForm()
    
    context = {
        "form": form,
        "title": "Create Insurance Provider",
        "submit_text": "Create Provider",
    }
    
    return render(request, "billing/insurance/form.html", context)


@login_required
def insurance_update_view(request, pk):
    """
    Update an existing insurance provider.
    
    Features:
    - Ownership verification
    - Form pre-population
    - Change tracking
    """
    
    # Validate vendor
    vendor = getattr(request.user, "vendor", None)
    if vendor is None:
        raise PermissionDenied("Only vendors can update insurance providers.")
    
    # Get provider
    try:
        provider = InsuranceProvider.objects.get(pk=pk, vendor=vendor)
    except InsuranceProvider.DoesNotExist:
        messages.error(request, "Insurance provider not found.")
        return redirect('billing:insurance_list')
    
    if request.method == "POST":
        form = InsuranceProviderForm(request.POST, instance=provider, vendor=vendor)
        
        if form.is_valid():
            # Check for duplicate code (excluding current provider)
            code = form.cleaned_data['code']
            duplicate = InsuranceProvider.objects.filter(
                vendor=vendor,
                code=code
            ).exclude(pk=pk)
            
            if duplicate.exists():
                messages.error(
                    request,
                    f'Another insurance provider with code "{code}" already exists.'
                )
            else:
                updated_provider = form.save()
                messages.success(
                    request,
                    f'Insurance provider "{updated_provider.name}" updated successfully.'
                )
                return redirect('billing:insurance_detail', pk=updated_provider.pk)
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = InsuranceProviderForm(instance=provider, vendor=vendor)
    
    context = {
        "form": form,
        "provider": provider,
        "title": f"Edit: {provider.name}",
        "submit_text": "Update Provider",
    }
    
    return render(request, "billing/insurance/form.html", context)


@login_required
def insurance_delete_view(request, pk):
    """
    Delete an insurance provider with safety checks.
    
    Features:
    - Checks for existing invoices
    - Checks for billing records
    - Confirmation page
    - Safe deletion
    """
    
    # Validate vendor
    vendor = getattr(request.user, "vendor", None)
    if vendor is None:
        raise PermissionDenied("Only vendors can delete insurance providers.")
    
    # Get provider
    try:
        provider = InsuranceProvider.objects.get(pk=pk, vendor=vendor)
    except InsuranceProvider.DoesNotExist:
        messages.error(request, "Insurance provider not found.")
        return redirect('billing:insurance_list')
    
    # Safety checks
    invoice_count = provider.invoices.count()
    billing_count = BillingInformation.objects.filter(
        vendor=vendor,
        insurance_provider=provider
    ).count()
    
    in_use = invoice_count > 0 or billing_count > 0
    
    if request.method == "POST":
        if in_use:
            messages.error(
                request,
                f'Cannot delete "{provider.name}" - it has {invoice_count} invoice(s) '
                f'and {billing_count} billing record(s).'
            )
            return redirect('billing:insurance_detail', pk=pk)
        
        provider_name = provider.name
        provider.delete()
        
        messages.success(
            request,
            f'Insurance provider "{provider_name}" has been deleted.'
        )
        return redirect('billing:insurance_list')
    
    context = {
        "provider": provider,
        "in_use": in_use,
        "invoice_count": invoice_count,
        "billing_count": billing_count,
    }
    
    return render(request, "billing/insurance/delete_confirm.html", context)


# Toggle active
@login_required
def insurance_toggle_active_view(request, pk):
    """
    Toggle the is_active status of an insurance provider.
    Quick enable/disable without full edit.
    """
    
    vendor = getattr(request.user, "vendor", None)
    if vendor is None:
        raise PermissionDenied("Only vendors can modify insurance providers.")
    
    try:
        provider = InsuranceProvider.objects.get(pk=pk, vendor=vendor)
    except InsuranceProvider.DoesNotExist:
        messages.error(request, "Insurance provider not found.")
        return redirect('billing:insurance_list')
    
    # Toggle status
    provider.is_active = not provider.is_active
    provider.save(update_fields=['is_active'])
    
    status = "activated" if provider.is_active else "deactivated"
    messages.success(
        request,
        f'Insurance provider "{provider.name}" has been {status}.'
    )
    
    # Redirect back
    # return redirect(request.META.get('HTTP_REFERER', 'billing:insurance_detail'), pk=pk)
    return redirect(request.META.get('HTTP_REFERER', reverse('billing:insurance_detail', args=[pk])))


# Financial Report...
@login_required
def insurance_financial_report_view(request, pk):
    """
    Generate detailed financial report for an insurance provider.
    
    Features:
    - Date range filtering
    - Invoice summary
    - Payment history
    - Aging analysis
    - Export options (future)
    """
    
    vendor = getattr(request.user, "vendor", None)
    if vendor is None:
        raise PermissionDenied("Only vendors can view financial reports.")
    
    try:
        provider = InsuranceProvider.objects.get(pk=pk, vendor=vendor)
    except InsuranceProvider.DoesNotExist:
        messages.error(request, "Insurance provider not found.")
        return redirect('billing:insurance_list')
    
    # Date range
    from datetime import datetime, timedelta
    from django.utils import timezone
    
    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")
    
    if date_from:
        date_from = datetime.strptime(date_from, "%Y-%m-%d").date()
    else:
        date_from = timezone.now().date() - timedelta(days=90)
    
    if date_to:
        date_to = datetime.strptime(date_to, "%Y-%m-%d").date()
    else:
        date_to = timezone.now().date()
    
    # Invoices in date range
    invoices = provider.invoices.filter(
        invoice_date__range=[date_from, date_to]
    ).order_by('-invoice_date')
    
    # Summary statistics
    invoice_summary = invoices.aggregate(
        total_invoices=Count('id'),
        total_amount=Sum('total_amount'),
        total_paid=Sum('amount_paid'),
    )
    
    outstanding = (invoice_summary['total_amount'] or Decimal('0')) - \
                  (invoice_summary['total_paid'] or Decimal('0'))
    
    # Aging analysis
    today = timezone.now().date()
    aging = {
        'current': Decimal('0'),      # 0-30 days
        'days_30_60': Decimal('0'),   # 30-60 days
        'days_60_90': Decimal('0'),   # 60-90 days
        'over_90': Decimal('0'),      # 90+ days
    }
    
    for invoice in invoices.filter(status__in=['SENT', 'PARTIAL', 'OVERDUE']):
        balance = invoice.balance_due()
        days_overdue = (today - invoice.due_date).days
        
        if days_overdue <= 30:
            aging['current'] += balance
        elif days_overdue <= 60:
            aging['days_30_60'] += balance
        elif days_overdue <= 90:
            aging['days_60_90'] += balance
        else:
            aging['over_90'] += balance
    
    context = {
        "provider": provider,
        "date_from": date_from,
        "date_to": date_to,
        "invoices": invoices,
        "invoice_summary": invoice_summary,
        "outstanding": outstanding,
        "aging": aging,
    }
    
    return render(request, "billing/insurance/financial_report.html", context)


# BULK ACTIONS
@login_required
def insurance_bulk_deactivate_view(request):
    """
    Bulk deactivate inactive insurance providers.
    Useful for cleanup.
    """
    
    vendor = getattr(request.user, "vendor", None)
    if vendor is None:
        raise PermissionDenied("Only vendors can perform bulk actions.")
    
    if request.method == "POST":
        provider_ids = request.POST.getlist('provider_ids')
        
        if provider_ids:
            count = InsuranceProvider.objects.filter(
                vendor=vendor,
                id__in=provider_ids
            ).update(is_active=False)
            
            messages.success(
                request,
                f'{count} insurance provider(s) deactivated.'
            )
        else:
            messages.warning(request, 'No providers selected.')
    
    return redirect('billing:insurance_list')

