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

from ..models import PriceList

from ..forms import PriceListForm



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

