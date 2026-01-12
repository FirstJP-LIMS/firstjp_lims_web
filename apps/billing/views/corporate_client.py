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
# CORPORATE CLIENT
# ==========================================

@login_required
def corporate_list_view(request):
    """
    List all corporate clients with filters and search.
    
    Features:
    - Search by company name, contact person, account number
    - Filter by active status
    - Sort by name, outstanding balance, credit limit
    - Credit limit warnings
    - Pagination
    - Quick stats
    """
    
    # Validate vendor
    vendor = getattr(request.user, "vendor", None)
    if vendor is None:
        raise PermissionDenied("Only vendors can access corporate clients.")
    
    # Base queryset
    queryset = CorporateClient.objects.filter(vendor=vendor).select_related('price_list')
    
    # Search across multiple fields
    q = request.GET.get("q")
    if q:
        queryset = queryset.filter(
            Q(company_name__icontains=q) |
            Q(contact_person__icontains=q) |
            Q(email__icontains=q) |
            Q(bank_account_number__icontains=q)
        )
    
    # Filter by active status
    is_active = request.GET.get("active")
    if is_active == "yes":
        queryset = queryset.filter(is_active=True)
    elif is_active == "no":
        queryset = queryset.filter(is_active=False)
    
    # Sort options
    sort = request.GET.get("sort", "name")
    if sort == "name":
        queryset = queryset.order_by("company_name")
    elif sort == "credit":
        queryset = queryset.order_by("-credit_limit")
    elif sort == "recent":
        queryset = queryset.order_by("-created_at")
    else:
        queryset = queryset.order_by("company_name")
    
    # Pagination
    paginator = Paginator(queryset, 20)
    page_obj = paginator.get_page(request.GET.get("page"))
    
    # Calculate stats for each client
    for client in page_obj:
        client.outstanding = client.get_outstanding_balance()
        client.over_limit = client.outstanding > client.credit_limit
        client.invoice_count = client.invoices.filter(
            status__in=['SENT', 'PARTIAL', 'OVERDUE']
        ).count()
        client.credit_used_pct = (
            (client.outstanding / client.credit_limit * 100) 
            if client.credit_limit > 0 else 0
        )
    
    # Summary statistics
    total_clients = queryset.count()
    active_count = queryset.filter(is_active=True).count()
    total_credit_limit = queryset.aggregate(total=Sum('credit_limit'))['total'] or Decimal('0')
    
    context = {
        "clients": page_obj,
        "page_obj": page_obj,
        "paginator": paginator,
        "q": q or "",
        "is_active": is_active or "",
        "sort": sort,
        "total_clients": total_clients,
        "active_count": active_count,
        "total_credit_limit": total_credit_limit,
    }
    
    return render(request, "billing/corporate/list.html", context)


@login_required
def corporate_detail_view(request, pk):
    """
    View corporate client details with comprehensive financial summary.
    
    Features:
    - Outstanding balance and credit utilization
    - Recent invoices with filtering
    - Recent billing records
    - Employee billing summary
    - Financial statistics
    """
    
    # Validate vendor
    vendor = getattr(request.user, "vendor", None)
    if vendor is None:
        raise PermissionDenied("Only vendors can view corporate clients.")
    
    # Get client
    try:
        client = CorporateClient.objects.select_related('price_list').get(
            pk=pk,
            vendor=vendor
        )
    except CorporateClient.DoesNotExist:
        messages.error(request, "Corporate client not found.")
        return redirect('billing:corporate_list')
    
    # Financial summary
    outstanding_balance = client.get_outstanding_balance()
    credit_available = client.credit_limit - outstanding_balance
    credit_used_pct = (
        (outstanding_balance / client.credit_limit * 100) 
        if client.credit_limit > 0 else 0
    )
    
    # Invoices with filtering
    invoices = client.invoices.order_by('-invoice_date')
    invoice_status = request.GET.get("invoice_status")
    if invoice_status:
        invoices = invoices.filter(status=invoice_status)
    
    # Pagination for invoices
    invoice_paginator = Paginator(invoices, 10)
    invoice_page_obj = invoice_paginator.get_page(request.GET.get("invoice_page"))
    
    # Recent billing records
    recent_billings = BillingInformation.objects.filter(
        vendor=vendor,
        corporate_client=client
    ).select_related('request').order_by('-created_at')[:10]
    
    # Employee billing summary (group by employee_id)
    employee_summary = BillingInformation.objects.filter(
        vendor=vendor,
        corporate_client=client,
        employee_id__isnull=False
    ).exclude(employee_id='').values('employee_id').annotate(
        total_tests=Count('id'),
        total_amount=Sum('total_amount')
    ).order_by('-total_amount')[:10]
    
    # Invoice statistics
    invoice_stats = client.invoices.aggregate(
        total_invoices=Count('id'),
        total_amount=Sum('total_amount'),
        paid_amount=Sum('amount_paid'),
        unpaid_count=Count('id', filter=Q(status__in=['SENT', 'OVERDUE', 'PARTIAL']))
    )
    
    # Billing statistics
    billing_stats = BillingInformation.objects.filter(
        vendor=vendor,
        corporate_client=client
    ).aggregate(
        total_billings=Count('id'),
        total_amount=Sum('total_amount'),
        total_employees=Count('employee_id', distinct=True)
    )
    
    context = {
        "client": client,
        "outstanding_balance": outstanding_balance,
        "credit_available": credit_available,
        "credit_used_pct": credit_used_pct,
        "invoices": invoice_page_obj,
        "invoice_page_obj": invoice_page_obj,
        "invoice_paginator": invoice_paginator,
        "recent_billings": recent_billings,
        "employee_summary": employee_summary,
        "invoice_stats": invoice_stats,
        "billing_stats": billing_stats,
        "invoice_status_filter": invoice_status or "",
    }
    
    return render(request, "billing/corporate/detail.html", context)


@login_required
def corporate_create_view(request):
    """
    Create a new corporate client.
    
    Features:
    - Vendor auto-assignment
    - Price list selection (vendor-specific)
    - Form validation
    - Duplicate account number checking
    """
    
    # Validate vendor
    vendor = getattr(request.user, "vendor", None)
    if vendor is None:
        raise PermissionDenied("Only vendors can create corporate clients.")
    
    if request.method == "POST":
        form = CorporateClientForm(request.POST, vendor=vendor)
        
        if form.is_valid():
            # Check for duplicate account number if provided
            account_number = form.cleaned_data.get('bank_account_number')
            if account_number:
                duplicate = CorporateClient.objects.filter(
                    vendor=vendor,
                    bank_account_number=account_number
                ).exists()
                
                if duplicate:
                    messages.error(
                        request,
                        f'A client with account number "{account_number}" already exists.'
                    )
                    # Re-render form with error
                    context = {
                        "form": form,
                        "title": "Create Corporate Client",
                        "submit_text": "Create Client",
                    }
                    return render(request, "billing/corporate/form.html", context)
            
            # Save client
            client = form.save(commit=False)
            client.vendor = vendor
            client.save()
            
            messages.success(
                request,
                f'Corporate client "{client.company_name}" created successfully.'
            )
            return redirect('billing:corporate_detail', pk=client.pk)
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = CorporateClientForm()
    
    context = {
        "form": form,
        "title": "Create Corporate Client",
        "submit_text": "Create Client",
    }
    
    return render(request, "billing/corporate/form.html", context)


@login_required
def corporate_update_view(request, pk):
    """
    Update an existing corporate client.
    
    Features:
    - Ownership verification
    - Form pre-population
    - Duplicate account number checking (excluding current)
    """
    
    # Validate vendor
    vendor = getattr(request.user, "vendor", None)
    if vendor is None:
        raise PermissionDenied("Only vendors can update corporate clients.")
    
    # Get client
    try:
        client = CorporateClient.objects.get(pk=pk, vendor=vendor)
    except CorporateClient.DoesNotExist:
        messages.error(request, "Corporate client not found.")
        return redirect('billing:corporate_list')
    
    if request.method == "POST":
        form = CorporateClientForm(request.POST, instance=client, vendor=vendor)
        
        if form.is_valid():
            # Check for duplicate account number (excluding current client)
            account_number = form.cleaned_data.get('bank_account_number')
            if account_number:
                duplicate = CorporateClient.objects.filter(
                    vendor=vendor,
                    bank_account_number=account_number
                ).exclude(pk=pk).exists()
                
                if duplicate:
                    messages.error(
                        request,
                        f'Another client with account number "{account_number}" already exists.'
                    )
                    context = {
                        "form": form,
                        "client": client,
                        "title": f"Edit: {client.company_name}",
                        "submit_text": "Update Client",
                    }
                    return render(request, "billing/corporate/form.html", context)
            
            updated_client = form.save()
            messages.success(
                request,
                f'Corporate client "{updated_client.company_name}" updated successfully.'
            )
            return redirect('billing:corporate_detail', pk=updated_client.pk)
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = CorporateClientForm(instance=client, vendor=vendor)
    
    context = {
        "form": form,
        "client": client,
        "title": f"Edit: {client.company_name}",
        "submit_text": "Update Client",
    }
    
    return render(request, "billing/corporate/form.html", context)


@login_required
def corporate_delete_view(request, pk):
    """
    Delete a corporate client with safety checks.
    
    Features:
    - Checks for existing invoices
    - Checks for billing records
    - Confirmation page
    - Safe deletion
    """
    
    # Validate vendor
    vendor = getattr(request.user, "vendor", None)
    if vendor is None:
        raise PermissionDenied("Only vendors can delete corporate clients.")
    
    # Get client
    try:
        client = CorporateClient.objects.get(pk=pk, vendor=vendor)
    except CorporateClient.DoesNotExist:
        messages.error(request, "Corporate client not found.")
        return redirect('billing:corporate_list')
    
    # Safety checks
    invoice_count = client.invoices.count()
    billing_count = BillingInformation.objects.filter(
        vendor=vendor,
        corporate_client=client
    ).count()
    
    in_use = invoice_count > 0 or billing_count > 0
    
    if request.method == "POST":
        if in_use:
            messages.error(
                request,
                f'Cannot delete "{client.company_name}" - it has {invoice_count} invoice(s) '
                f'and {billing_count} billing record(s).'
            )
            return redirect('billing:corporate_detail', pk=pk)
        
        company_name = client.company_name
        client.delete()
        
        messages.success(
            request,
            f'Corporate client "{company_name}" has been deleted.'
        )
        return redirect('billing:corporate_list')
    
    context = {
        "client": client,
        "in_use": in_use,
        "invoice_count": invoice_count,
        "billing_count": billing_count,
    }
    
    return render(request, "billing/corporate/delete_confirm.html", context)


@login_required
def corporate_toggle_active_view(request, pk):
    """
    Toggle the is_active status of a corporate client.
    Quick enable/disable without full edit.
    """
    
    vendor = getattr(request.user, "vendor", None)
    if vendor is None:
        raise PermissionDenied("Only vendors can modify corporate clients.")
    
    try:
        client = CorporateClient.objects.get(pk=pk, vendor=vendor)
    except CorporateClient.DoesNotExist:
        messages.error(request, "Corporate client not found.")
        return redirect('billing:corporate_list')
    
    # Toggle status
    client.is_active = not client.is_active
    client.save(update_fields=['is_active', 'updated_at'])
    
    status = "activated" if client.is_active else "deactivated"
    messages.success(
        request,
        f'Corporate client "{client.company_name}" has been {status}.'
    )
    
    # Redirect back
    return redirect(request.META.get('HTTP_REFERER', 'billing:corporate_detail'), pk=pk)


@login_required
def corporate_employee_report_view(request, pk):
    """
    Generate employee billing report for a corporate client.
    
    Features:
    - List all employees with billing
    - Total tests per employee
    - Total amount per employee
    - Date range filtering
    - Export capability
    """
    
    vendor = getattr(request.user, "vendor", None)
    if vendor is None:
        raise PermissionDenied("Only vendors can view reports.")
    
    try:
        client = CorporateClient.objects.get(pk=pk, vendor=vendor)
    except CorporateClient.DoesNotExist:
        messages.error(request, "Corporate client not found.")
        return redirect('billing:corporate_list')
    
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
    
    # Get employee billing data
    employee_data = BillingInformation.objects.filter(
        vendor=vendor,
        corporate_client=client,
        created_at__date__range=[date_from, date_to],
        employee_id__isnull=False
    ).exclude(employee_id='').values('employee_id').annotate(
        test_count=Count('id'),
        total_amount=Sum('total_amount'),
        paid_amount=Sum('total_amount', filter=Q(payment_status='PAID')),
        last_visit=models.Max('created_at')
    ).order_by('-total_amount')
    
    # Pagination
    paginator = Paginator(employee_data, 25)
    page_obj = paginator.get_page(request.GET.get("page"))
    
    # Summary
    summary = BillingInformation.objects.filter(
        vendor=vendor,
        corporate_client=client,
        created_at__date__range=[date_from, date_to]
    ).aggregate(
        total_employees=Count('employee_id', distinct=True, filter=Q(employee_id__isnull=False)),
        total_tests=Count('id'),
        total_amount=Sum('total_amount')
    )
    
    context = {
        "client": client,
        "date_from": date_from,
        "date_to": date_to,
        "employee_data": page_obj,
        "page_obj": page_obj,
        "paginator": paginator,
        "summary": summary,
    }
    
    return render(request, "billing/corporate/employee_report.html", context)


@login_required
def corporate_financial_report_view(request, pk):
    """
    Generate comprehensive financial report for corporate client.
    Similar to insurance financial report with aging analysis.
    """
    
    vendor = getattr(request.user, "vendor", None)
    if vendor is None:
        raise PermissionDenied("Only vendors can view financial reports.")
    
    try:
        client = CorporateClient.objects.get(pk=pk, vendor=vendor)
    except CorporateClient.DoesNotExist:
        messages.error(request, "Corporate client not found.")
        return redirect('billing:corporate_list')
    
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
    invoices = client.invoices.filter(
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
        'current': Decimal('0'),
        'days_30_60': Decimal('0'),
        'days_60_90': Decimal('0'),
        'over_90': Decimal('0'),
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
        "client": client,
        "date_from": date_from,
        "date_to": date_to,
        "invoices": invoices,
        "invoice_summary": invoice_summary,
        "outstanding": outstanding,
        "aging": aging,
    }
    
    return render(request, "billing/corporate/financial_report.html", context)
