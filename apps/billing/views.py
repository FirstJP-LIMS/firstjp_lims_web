from decimal import Decimal
from datetime import datetime, timedelta, date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import models, transaction
from django.db.models import Q, Sum, Count, Avg
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy, reverse
from django.utils import timezone
from django.views.generic import (
    ListView, DetailView, CreateView, UpdateView, DeleteView, View
)

from .models import (
    PriceList, TestPrice, InsuranceProvider, CorporateClient,
    BillingInformation, Payment, Invoice, InvoicePayment, D
)

from .forms import (
    PriceListForm, TestPriceForm, InsuranceProviderForm, CorporateClientForm,
    BillingInformationForm, PaymentForm, InvoiceForm, InvoicePaymentForm,
    BillingFilterForm, InvoiceFilterForm
)

from .utils import generate_invoice_pdf, generate_receipt_pdf


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

# ==========================================
# PRICE LIST VIEWS
# ==========================================

@login_required
def pricelist_list_view(request):
    """
    Includes: Vendor permission check, Search (q), Filter by type (?type=), Ordering, Pagination
    """
    # -------------------------------
    # Validate Vendor
    # -------------------------------
    vendor = getattr(request.user, "vendor", None)
    if vendor is None:
        # STRICT VERSION (BLOCK NON-VENDORS)
        raise PermissionDenied("Only vendors can access price lists.")    
    # -------------------------------
    # Base Queryset
    # -------------------------------
    queryset = PriceList.objects.filter(vendor=vendor)
    # -------------------------------
    # Search by name
    # -------------------------------
    q = request.GET.get("q")
    if q:
        queryset = queryset.filter(name__icontains=q)

    # Filter by price list type  
    # e.g.:  /billing/pricelists/?type=HMO
    price_type = request.GET.get("type")
    if price_type:
        queryset = queryset.filter(price_type=price_type)

    # Add ordering
    queryset = queryset.order_by("price_type", "name").prefetch_related("test_prices")

    # Pagination (20 per page)
    paginator = Paginator(queryset, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {
        "pricelists": page_obj,
        "page_obj": page_obj,
        "paginator": paginator,
        "q": q or "",
        "filter_type": price_type or "",
    }

    return render(request, "billing/pricelist/list.html", context)


@login_required
def pricelist_create_view(request):
    """
    Create a new price list.
    Features: Vendor permission check, Form validation, Auto-assign vendor, Success message, Redirect to list view
    """
    # -------------------------------
    # Validate Vendor
    # -------------------------------
    vendor = getattr(request.user, "vendor", None)
    if vendor is None:
        raise PermissionDenied("Only vendors can create price lists.")
    
    # -------------------------------
    # Handle POST (Form Submission)
    # -------------------------------
    if request.method == "POST":
        form = PriceListForm(request.POST)
        
        if form.is_valid():
            # Create but don't save yet
            pricelist = form.save(commit=False)
            pricelist.vendor = vendor            
            pricelist.save()
            
            # Success message
            messages.success(
                request,
                f'Price list "{pricelist.name}" created successfully.'
            )
            # Redirect to list view
            return redirect('billing:pricelist_list')
        else:
            # Form has errors - will be displayed in template
            messages.error(request, 'Please correct the errors below.')
    # -------------------------------
    # Handle GET (Show Empty Form)
    # -------------------------------
    else:
        form = PriceListForm()
    
    context = {
        "form": form,
        "title": "Create Price List",
        "submit_text": "Create Price List",
    }
    
    return render(request, "billing/pricelist/form.html", context)


@login_required
def pricelist_update_view(request, pk):
    """
    Update an existing price list.
    Features:
    - Vendor permission check (can only edit own price lists)
    - Form validation
    - Success message
    - Redirect to detail or list view
    """
    
    # -------------------------------
    # Validate Vendor & Get Object
    # -------------------------------
    vendor = getattr(request.user, "vendor", None)
    if vendor is None:
        raise PermissionDenied("Only vendors can update price lists.")
    
    # Get the price list, ensuring it belongs to this vendor
    try:
        pricelist = PriceList.objects.get(pk=pk, vendor=vendor)
    except PriceList.DoesNotExist:
        messages.error(request, "Price list not found or you don't have permission to edit it.")
        return redirect('billing:pricelist_list')
    
    # -------------------------------
    # Handle POST (Form Submission)
    # -------------------------------
    if request.method == "POST":
        form = PriceListForm(request.POST, instance=pricelist)
        
        if form.is_valid():
            # Save the updated price list
            updated_pricelist = form.save()
            
            # Success message
            messages.success(
                request,
                f'Price list "{updated_pricelist.name}" updated successfully.'
            )
            
            # Redirect to detail
            return redirect('billing:pricelist_detail', pk=updated_pricelist.pk)
        
        else:
            messages.error(request, 'Please correct the errors below.')
    
    # -------------------------------
    # Handle GET (Show Form with Data)
    # -------------------------------
    else:
        form = PriceListForm(instance=pricelist)
    
    context = {
        "form": form,
        "pricelist": pricelist,
        "title": f"Edit Price List: {pricelist.name}",
        "submit_text": "Update Price List",
    }
    
    return render(request, "billing/pricelist/form.html", context)


@login_required
def pricelist_detail_view(request, pk):
    """
    View price list details with all test prices.
    
    Features:
    - Vendor permission check
    - Display all test prices in this price list
    - Pagination for test prices
    - Quick stats (total tests, average price, etc.)
    """
    
    # -------------------------------
    # Validate Vendor & Get Object
    # -------------------------------
    vendor = getattr(request.user, "vendor", None)
    if vendor is None:
        raise PermissionDenied("Only vendors can view price lists.")
    
    try:
        pricelist = PriceList.objects.prefetch_related(
            'test_prices__test'
        ).get(pk=pk, vendor=vendor)
    except PriceList.DoesNotExist:
        messages.error(request, "Price list not found.")
        return redirect('billing:pricelist_list')
    
    # -------------------------------
    # Get Test Prices with Search/Filter
    # -------------------------------
    test_prices = pricelist.test_prices.all()
    
    # Search by test name or code
    q = request.GET.get("q")
    if q:
        test_prices = test_prices.filter(
            models.Q(test__name__icontains=q) |
            models.Q(test__code__icontains=q)
        )
    
    # Order by test name
    test_prices = test_prices.order_by('test__name')
    
    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(test_prices, 25)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    
    # -------------------------------
    # Calculate Statistics
    # -------------------------------
    stats = pricelist.test_prices.aggregate(
        total_tests=Count('id'),
        avg_price=Avg('price'),
        total_value=Sum('price')
    )
    
    context = {
        "pricelist": pricelist,
        "test_prices": page_obj,
        "page_obj": page_obj,
        "paginator": paginator,
        "q": q or "",
        "stats": stats,
    }
    
    return render(request, "billing/pricelist/detail.html", context)


@login_required
def pricelist_delete_view(request, pk):
    """
    Delete a price list (with confirmation).
    
    Features:
    - Vendor permission check
    - Confirmation page (GET)
    - Actual deletion (POST)
    - Check if price list is in use
    """
    
    # -------------------------------
    # Validate Vendor & Get Object
    # -------------------------------
    vendor = getattr(request.user, "vendor", None)
    if vendor is None:
        raise PermissionDenied("Only vendors can delete price lists.")
    
    try:
        pricelist = PriceList.objects.get(pk=pk, vendor=vendor)
    except PriceList.DoesNotExist:
        messages.error(request, "Price list not found.")
        return redirect('billing:pricelist_list')
    
    # -------------------------------
    # Check if Price List is in Use
    # -------------------------------
    # Check if any billing records use this price list
    billing_count = pricelist.billinginformation_set.count()
    
    # Check if any insurance providers use this price list
    insurance_count = pricelist.insuranceprovider_set.count()
    
    # Check if any corporate clients use this price list
    corporate_count = pricelist.corporateclient_set.count()
    
    in_use = billing_count > 0 or insurance_count > 0 or corporate_count > 0
    
    # -------------------------------
    # Handle POST (Actual Deletion)
    # -------------------------------
    if request.method == "POST":
        if in_use:
            messages.error(
                request,
                f'Cannot delete "{pricelist.name}" because it is currently in use.'
            )
            return redirect('billing:pricelist_detail', pk=pk)
        
        # Safe to delete
        pricelist_name = pricelist.name
        pricelist.delete()
        
        messages.success(
            request,
            f'Price list "{pricelist_name}" has been deleted.'
        )
        
        return redirect('billing:pricelist_list')
    
    # -------------------------------
    # Handle GET (Confirmation Page)
    # -------------------------------
    context = {
        "pricelist": pricelist,
        "in_use": in_use,
        "billing_count": billing_count,
        "insurance_count": insurance_count,
        "corporate_count": corporate_count,
    }  
    return render(request, "billing/pricelist/delete_confirm.html", context)


# Toggle Active Status
@login_required
def pricelist_toggle_active_view(request, pk):
    """
    Toggle the is_active status of a price list.
    Useful for quickly enabling/disabling price lists.
    """
    
    vendor = getattr(request.user, "vendor", None)
    if vendor is None:
        raise PermissionDenied("Only vendors can modify price lists.")
    
    try:
        pricelist = PriceList.objects.get(pk=pk, vendor=vendor)
    except PriceList.DoesNotExist:
        messages.error(request, "Price list not found.")
        return redirect('billing:pricelist_list')
    
    # Toggle the active status
    pricelist.is_active = not pricelist.is_active
    pricelist.save(update_fields=['is_active', 'updated_at'])
    
    status = "activated" if pricelist.is_active else "deactivated"
    messages.success(
        request,
        f'Price list "{pricelist.name}" has been {status}.'
    )
    
    # Redirect back to the referring page or detail page
    # return redirect(request.META.get('HTTP_REFERER', 'billing:pricelist_detail'), pk=pk)
    return redirect(request.META.get('HTTP_REFERER', reverse('billing:pricelist_detail', args=[pk])))


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

# class CorporateClientListView(LoginRequiredMixin, ListView):
#     """List all corporate clients"""
#     model = CorporateClient
#     template_name = 'billing/corporate_list.html'
#     context_object_name = 'clients'
#     paginate_by = 20
    
#     def get_queryset(self):
#         return CorporateClient.objects.filter(
#             vendor=self.request.user.vendor
#         ).select_related('price_list')


# class CorporateClientDetailView(LoginRequiredMixin, DetailView):
#     """View corporate client details"""
#     model = CorporateClient
#     template_name = 'billing/corporate_detail.html'
#     context_object_name = 'client'
    
#     def get_queryset(self):
#         return CorporateClient.objects.filter(vendor=self.request.user.vendor)
    
#     def get_context_data(self, **kwargs):
#         context = super().get_context_data(**kwargs)
#         client = self.object
        
#         # Outstanding balance
#         context['outstanding_balance'] = client.get_outstanding_balance()
        
#         # Recent invoices
#         context['recent_invoices'] = client.invoices.order_by('-invoice_date')[:10]
        
#         return context


# class CorporateClientCreateView(LoginRequiredMixin, CreateView):
#     """Create new corporate client"""
#     model = CorporateClient
#     form_class = CorporateClientForm
#     template_name = 'billing/corporate_form.html'
#     success_url = reverse_lazy('billing:corporate_list')
    
#     def form_valid(self, form):
#         form.instance.vendor = self.request.user.vendor
#         messages.success(self.request, 'Corporate client created successfully.')
#         return super().form_valid(form)


# class CorporateClientUpdateView(LoginRequiredMixin, UpdateView):
#     """Update corporate client"""
#     model = CorporateClient
#     form_class = CorporateClientForm
#     template_name = 'billing/corporate_form.html'
#     success_url = reverse_lazy('billing:corporate_list')
    
#     def get_queryset(self):
#         return CorporateClient.objects.filter(vendor=self.request.user.vendor)
    
#     def form_valid(self, form):
#         messages.success(self.request, 'Corporate client updated successfully.')
#         return super().form_valid(form)


# ==========================================
# BILLING INFORMATION VIEWS
# ==========================================

class BillingListView(LoginRequiredMixin, ListView):
    """List all billing records with filters"""
    model = BillingInformation
    template_name = 'billing/billing_list.html'
    context_object_name = 'billings'
    paginate_by = 25
    
    def get_queryset(self):
        queryset = BillingInformation.objects.filter(
            vendor=self.request.user.vendor
        ).select_related(
            'request', 'price_list', 'insurance_provider', 'corporate_client'
        ).order_by('-created_at')
        
        # Apply filters
        form = BillingFilterForm(self.request.GET)
        if form.is_valid():
            if form.cleaned_data.get('billing_type'):
                queryset = queryset.filter(billing_type=form.cleaned_data['billing_type'])
            
            if form.cleaned_data.get('payment_status'):
                queryset = queryset.filter(payment_status=form.cleaned_data['payment_status'])
            
            if form.cleaned_data.get('date_from'):
                queryset = queryset.filter(created_at__date__gte=form.cleaned_data['date_from'])
            
            if form.cleaned_data.get('date_to'):
                queryset = queryset.filter(created_at__date__lte=form.cleaned_data['date_to'])
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter_form'] = BillingFilterForm(self.request.GET)
        return context


class BillingDetailView(LoginRequiredMixin, DetailView):
    """View billing record details"""
    model = BillingInformation
    template_name = 'billing/billing_detail.html'
    context_object_name = 'billing'
    
    def get_queryset(self):
        return BillingInformation.objects.filter(
            vendor=self.request.user.vendor
        ).select_related(
            'request', 'price_list', 'insurance_provider', 'corporate_client'
        ).prefetch_related('payments', 'request__test_assignments__test')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        billing = self.object
        
        context['balance_due'] = billing.get_balance_due()
        context['payment_form'] = PaymentForm(billing=billing)
        
        return context


class BillingUpdateView(LoginRequiredMixin, UpdateView):
    """Update billing information"""
    model = BillingInformation
    form_class = BillingInformationForm
    template_name = 'billing/billing_form.html'
    
    def get_queryset(self):
        return BillingInformation.objects.filter(vendor=self.request.user.vendor)
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['vendor'] = self.request.user.vendor
        return kwargs
    
    def get_success_url(self):
        return reverse('billing:billing_detail', kwargs={'pk': self.object.pk})
    
    def form_valid(self, form):
        messages.success(self.request, 'Billing information updated successfully.')
        return super().form_valid(form)


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
# INVOICE VIEWS
# ==========================================

class InvoiceListView(LoginRequiredMixin, ListView):
    """List all invoices with filters"""
    model = Invoice
    template_name = 'billing/invoice_list.html'
    context_object_name = 'invoices'
    paginate_by = 25
    
    def get_queryset(self):
        queryset = Invoice.objects.filter(
            vendor=self.request.user.vendor
        ).select_related(
            'insurance_provider', 'corporate_client', 'created_by'
        ).order_by('-invoice_date')
        
        # Apply filters
        form = InvoiceFilterForm(self.request.GET)
        if form.is_valid():
            if form.cleaned_data.get('status'):
                queryset = queryset.filter(status=form.cleaned_data['status'])
            
            client_type = form.cleaned_data.get('client_type')
            if client_type == 'HMO':
                queryset = queryset.filter(insurance_provider__isnull=False)
            elif client_type == 'CORPORATE':
                queryset = queryset.filter(corporate_client__isnull=False)
            
            if form.cleaned_data.get('date_from'):
                queryset = queryset.filter(invoice_date__gte=form.cleaned_data['date_from'])
            
            if form.cleaned_data.get('date_to'):
                queryset = queryset.filter(invoice_date__lte=form.cleaned_data['date_to'])
        
        # Check for overdue invoices
        for invoice in queryset:
            if invoice.is_overdue() and invoice.status not in ['PAID', 'CANCELLED']:
                invoice.status = 'OVERDUE'
                invoice.save(update_fields=['status'])
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter_form'] = InvoiceFilterForm(self.request.GET)
        return context


class InvoiceDetailView(LoginRequiredMixin, DetailView):
    """View invoice details"""
    model = Invoice
    template_name = 'billing/invoice_detail.html'
    context_object_name = 'invoice'
    
    def get_queryset(self):
        return Invoice.objects.filter(
            vendor=self.request.user.vendor
        ).select_related(
            'insurance_provider', 'corporate_client'
        ).prefetch_related('billing_records', 'payments')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        invoice = self.object
        
        context['balance_due'] = invoice.balance_due()
        context['payment_form'] = InvoicePaymentForm(invoice=invoice)
        
        return context


class InvoiceCreateView(LoginRequiredMixin, CreateView):
    """Create new invoice"""
    model = Invoice
    form_class = InvoiceForm
    template_name = 'billing/invoice_form.html'
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['vendor'] = self.request.user.vendor
        return kwargs
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get pending billing records for invoice generation
        vendor = self.request.user.vendor
        pending_hmo = BillingInformation.objects.filter(
            vendor=vendor,
            billing_type='HMO',
            payment_status='INVOICED',
            invoices__isnull=True
        ).select_related('insurance_provider')
        
        pending_corporate = BillingInformation.objects.filter(
            vendor=vendor,
            billing_type='CORPORATE',
            payment_status='INVOICED',
            invoices__isnull=True
        ).select_related('corporate_client')
        
        context['pending_hmo'] = pending_hmo
        context['pending_corporate'] = pending_corporate
        
        return context
    
    def form_valid(self, form):
        with transaction.atomic():
            form.instance.vendor = self.request.user.vendor
            form.instance.created_by = self.request.user
            
            # Generate invoice number
            last_invoice = Invoice.objects.filter(
                vendor=self.request.user.vendor
            ).order_by('-id').first()
            
            if last_invoice and last_invoice.invoice_number:
                try:
                    last_num = int(last_invoice.invoice_number.split('-')[-1])
                    new_num = last_num + 1
                except (ValueError, IndexError):
                    new_num = 1
            else:
                new_num = 1
            
            form.instance.invoice_number = f"INV-{timezone.now().year}-{new_num:05d}"
            
            self.object = form.save()
            
            # Link billing records
            billing_ids = self.request.POST.getlist('billing_records')
            if billing_ids:
                billing_records = BillingInformation.objects.filter(
                    id__in=billing_ids,
                    vendor=self.request.user.vendor
                )
                self.object.billing_records.set(billing_records)
                
                # Calculate totals
                self.object.calculate_totals()
            
            messages.success(self.request, f'Invoice {self.object.invoice_number} created successfully.')
            return redirect('billing:invoice_detail', pk=self.object.pk)


class InvoicePaymentCreateView(LoginRequiredMixin, View):
    """Record invoice payment"""
    
    def post(self, request, invoice_pk):
        invoice = get_object_or_404(
            Invoice,
            pk=invoice_pk,
            vendor=request.user.vendor
        )
        
        form = InvoicePaymentForm(request.POST, invoice=invoice)
        
        if form.is_valid():
            with transaction.atomic():
                payment = form.save(commit=False)
                payment.invoice = invoice
                payment.recorded_by = request.user
                payment.save()
                
                messages.success(request, f'Payment of ₦{payment.amount:,.2f} recorded successfully.')
                return redirect('billing:invoice_detail', pk=invoice.pk)
        else:
            messages.error(request, 'Error recording payment. Please check the form.')
            return redirect('billing:invoice_detail', pk=invoice.pk)


# ==========================================
# PDF GENERATION VIEWS
# ==========================================

class GenerateInvoicePDFView(LoginRequiredMixin, View):
    """Generate and download invoice PDF"""
    
    def get(self, request, invoice_pk):
        invoice = get_object_or_404(
            Invoice,
            pk=invoice_pk,
            vendor=request.user.vendor
        )
        
        pdf = generate_invoice_pdf(invoice)
        
        response = HttpResponse(pdf, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="invoice_{invoice.invoice_number}.pdf"'
        
        return response


class GenerateReceiptPDFView(LoginRequiredMixin, View):
    """Generate and download payment receipt PDF"""
    
    def get(self, request, payment_pk):
        payment = get_object_or_404(
            Payment,
            pk=payment_pk,
            billing__vendor=request.user.vendor
        )
        
        pdf = generate_receipt_pdf(payment)
        
        response = HttpResponse(pdf, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="receipt_{payment.pk}.pdf"'
        
        return response


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