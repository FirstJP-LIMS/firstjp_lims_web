from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Sum, F, Count, ExpressionWrapper, DecimalField
from django.utils import timezone
from django.http import JsonResponse, HttpResponse
from django.core.paginator import Paginator
from datetime import timedelta
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.db import transaction, IntegrityError
from django.urls import reverse
import csv

from .models import (
    InventoryCategory, InventoryItem, StockLot, ReagentUsage,
    StockAdjustment, PurchaseOrder, PurchaseOrderItem,
    StorageUnit, StorageLocation, StoredSample
)
from .forms import (
    InventoryCategoryForm, InventoryItemForm, InventoryItemSearchForm,
    StockLotForm, StockLotSearchForm, ReagentUsageForm,
    StockAdjustmentForm, PurchaseOrderForm, PurchaseOrderItemFormSet,
    StorageUnitForm, StorageLocationForm, StoredSampleForm,
    StoredSampleRetrievalForm
)

# permission decorator
from .decorators import vendor_admin_required, vendor_staff_required

# ==========================================
# DASHBOARD
# ==========================================

@login_required
def inventory_dashboard(request):
    """Main inventory dashboard with key metrics"""
    vendor = request.user.vendor
    
    # Key Metrics
    total_items = InventoryItem.objects.filter(vendor=vendor, is_active=True).count()
    
    # Low stock items
    low_stock_items = []
    for item in InventoryItem.objects.filter(vendor=vendor, is_active=True):
        current_stock = item.get_current_stock()
        if current_stock <= item.reorder_level:
            low_stock_items.append(item)
    
    # Expiring soon (next 30 days)
    expiring_soon = StockLot.objects.filter(
        item__vendor=vendor,
        is_available=True,
        expiry_date__lte=timezone.now().date() + timedelta(days=30),
        expiry_date__gt=timezone.now().date()
    ).order_by('expiry_date')[:10]
    
    # Expired lots
    expired_lots = StockLot.objects.filter(
        item__vendor=vendor,
        expiry_date__lte=timezone.now().date(),
        status='EXPIRED'
    ).count()
    
    # Recent usage (last 7 days)
    recent_usage = ReagentUsage.objects.filter(
        stock_lot__item__vendor=vendor,
        used_at__gte=timezone.now() - timedelta(days=7)
    ).select_related('stock_lot__item').order_by('-used_at')[:10]
    
    # Pending purchase orders
    pending_pos = PurchaseOrder.objects.filter(
        vendor=vendor,
        status__in=['SUBMITTED', 'APPROVED', 'ORDERED']
    ).count()
    
    # Total inventory value
    inventory_value = StockLot.objects.filter(
        item__vendor=vendor,
        is_available=True
    ).annotate(
        lot_value=ExpressionWrapper(
            F('quantity_remaining') * F('unit_cost'),
            output_field=DecimalField()
        )
    ).aggregate(total=Sum('lot_value'))['total'] or 0
    
    context = {
        'total_items': total_items,
        'low_stock_count': len(low_stock_items),
        'low_stock_items': low_stock_items[:10],
        'expiring_soon_count': expiring_soon.count(),
        'expiring_soon': expiring_soon,
        'expired_lots': expired_lots,
        'recent_usage': recent_usage,
        'pending_pos': pending_pos,
        'inventory_value': inventory_value,
    }
    
    return render(request, 'inventory/dashboard.html', context)


# ==========================================
# INVENTORY CATEGORY VIEWS
# ==========================================

@login_required
def category_list(request):
    """List all inventory categories"""
    vendor = request.user.vendor
    
    # Get all categories with item counts
    categories = InventoryCategory.objects.filter(
        vendor=vendor
    ).annotate(
        item_count=Count('items'),
        active_item_count=Count('items', filter=Q(items__is_active=True))
    ).order_by('category_type', 'name')
    
    # Filter by category type if specified
    category_type = request.GET.get('category_type')
    if category_type:
        categories = categories.filter(category_type=category_type)
    
    # Search
    search = request.GET.get('search')
    if search:
        categories = categories.filter(
            Q(name__icontains=search) | Q(description__icontains=search)
        )
    
    # Pagination
    paginator = Paginator(categories, 20)
    page_number = request.GET.get('page')
    categories_page = paginator.get_page(page_number)
    
    # Get category type choices for filter
    category_types = InventoryCategory.CATEGORY_TYPES
    reagent_count = categories.filter(category_type='REAGENT').count()
    control_count = categories.filter(category_type='CONTROL').count()
    consumable_count = categories.filter(category_type='CONSUMABLE').count()
    
    context = {
        'categories': categories_page,
        'category_types': category_types,
        'current_type': category_type,
        'search_query': search,
        'reagent_count': reagent_count,
        'control_count': control_count,
        'consumable_count': consumable_count,
    }
    
    return render(request, 'inventory/category/category_list.html', context)


@login_required
@vendor_admin_required
def category_create(request):
    """Create a new inventory category"""
    if request.method == 'POST':
        form = InventoryCategoryForm(request.POST)
        if form.is_valid():
            category = form.save(commit=False)
            category.vendor = request.user.vendor
            try:
                category.save()
                messages.success(
                    request, 
                    f'Category "{category.name}" created successfully.'
                )
                return redirect('inventory:category_detail', pk=category.pk)
            except IntegrityError:
                messages.error(
                    request, 
                    f'A category with the name "{category.name}" already exists.'
                )
    else:
        form = InventoryCategoryForm()
    
    context = {
        'form': form,
        'title': 'Add New Category',
        'submit_text': 'Create Category'
    }
    return render(request, 'inventory/category/category_form.html', context)


@login_required
def category_detail(request, pk):
    """View details of a specific category"""
    category = get_object_or_404(
        InventoryCategory, 
        pk=pk, 
        vendor=request.user.vendor
    )
    
    # Get all items in this category
    items = category.items.all().select_related('category')
    
    # Calculate metrics
    total_items = items.count()
    active_items = items.filter(is_active=True).count()
    
    # Calculate total inventory value
    total_value = 0
    for item in items.filter(is_active=True):
        current_stock = item.get_current_stock()
        total_value += current_stock * item.unit_cost
    
    # Low stock items in this category
    low_stock_items = []
    for item in items.filter(is_active=True):
        if item.is_below_reorder_level():
            low_stock_items.append(item)
    
    # Pagination for items
    paginator = Paginator(items, 25)
    page_number = request.GET.get('page')
    items_page = paginator.get_page(page_number)
    
    context = {
        'category': category,
        'items': items_page,
        'total_items': total_items,
        'active_items': active_items,
        'inactive_items': total_items - active_items,
        'total_value': total_value,
        'low_stock_count': len(low_stock_items),
        'low_stock_items': low_stock_items[:5],  # Show first 5
    }
    
    return render(request, 'inventory/category/category_detail.html', context)


@login_required
@vendor_admin_required
def category_update(request, pk):
    """Update an inventory category - Only admins"""
    category = get_object_or_404(
        InventoryCategory, 
        pk=pk, 
        vendor=request.user.vendor
    )
    
    if request.method == 'POST':
        form = InventoryCategoryForm(request.POST, instance=category)
        if form.is_valid():
            try:
                form.save()
                messages.success(
                    request, 
                    f'Category "{category.name}" updated successfully.'
                )
                return redirect('inventory:category_detail', pk=category.pk)
            except IntegrityError:
                messages.error(
                    request, 
                    f'A category with the name "{category.name}" already exists.'
                )
    else:
        form = InventoryCategoryForm(instance=category)
    
    context = {
        'form': form,
        'category': category,
        'title': 'Edit Category',
        'submit_text': 'Update Category'
    }
    return render(request, 'inventory/category/category_form.html', context)


@login_required
@vendor_admin_required
def category_delete(request, pk):
    """Delete an inventory category"""
    category = get_object_or_404(
        InventoryCategory, 
        pk=pk, 
        vendor=request.user.vendor
    )
    
    # Check if category has items
    item_count = category.items.count()
    
    if request.method == 'POST':
        if item_count > 0:
            messages.error(
                request,
                f'Cannot delete "{category.name}" because it has {item_count} item(s). '
                'Please reassign or delete all items in this category first.'
            )
            return redirect('inventory:category_detail', pk=category.pk)
        
        category_name = category.name
        category.delete()
        messages.success(
            request, 
            f'Category "{category_name}" deleted successfully.'
        )
        return redirect('inventory:category_list')
    
    context = {
        'category': category,
        'item_count': item_count,
    }
    return render(request, 'inventory/category/confirm_delete.html', context)


@login_required
@vendor_admin_required
def category_items_export(request, pk):
    """Export all items in a category to CSV"""
    category = get_object_or_404(
        InventoryCategory, 
        pk=pk, 
        vendor=request.user.vendor
    )
    
    items = category.items.filter(is_active=True)
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="category_{category.name}_items.csv"'
    
    writer = csv.writer(response)
    writer.writerow([
        'Item Code', 'Name', 'Manufacturer', 'Current Stock',
        'Unit of Measure', 'Reorder Level', 'Unit Cost', 'Storage Condition'
    ])
    
    for item in items:
        writer.writerow([
            item.item_code,
            item.name,
            item.manufacturer,
            item.get_current_stock(),
            item.unit_of_measure,
            item.reorder_level,
            item.unit_cost,
            item.get_storage_condition_display(),
        ])
    
    return response


# ==========================================
# INVENTORY ITEMS
# ==========================================

@login_required
def inventory_item_list(request):
    """List all inventory items with search and filters"""
    vendor = request.user.vendor
    form = InventoryItemSearchForm(request.GET)
    
    items = InventoryItem.objects.filter(vendor=vendor).select_related('category')
    
    # Apply filters
    if form.is_valid():
        search = form.cleaned_data.get('search')
        category = form.cleaned_data.get('category')
        storage_condition = form.cleaned_data.get('storage_condition')
        status = form.cleaned_data.get('status')
        
        if search:
            items = items.filter(
                Q(name__icontains=search) |
                Q(item_code__icontains=search) |
                Q(manufacturer__icontains=search)
            )
        
        if category:
            items = items.filter(category=category)
        
        if storage_condition:
            items = items.filter(storage_condition=storage_condition)
        
        if status == 'active':
            items = items.filter(is_active=True)
        elif status == 'inactive':
            items = items.filter(is_active=False)
        elif status == 'low_stock':
            # Filter items with stock below reorder level
            low_stock_ids = []
            for item in items:
                if item.is_below_reorder_level():
                    low_stock_ids.append(item.id)
            items = items.filter(id__in=low_stock_ids)
        elif status == 'out_of_stock':
            out_stock_ids = []
            for item in items:
                if item.get_current_stock() == 0:
                    out_stock_ids.append(item.id)
            items = items.filter(id__in=out_stock_ids)
    
    # Pagination
    paginator = Paginator(items, 25)
    page_number = request.GET.get('page')
    items_page = paginator.get_page(page_number)
    
    context = {
        'items': items_page,
        'form': form,
    }
    
    # In your item_list view, add these calculations:
    # context = {
    #     'items': items_page,
    #     'form': form,
    #     'total_items': items_count,
    #     'active_items': items.filter(is_active=True).count(),
    #     'low_stock_items': low_stock_count,  # You'll need to calculate this
    #     'total_value': total_inventory_value,  # You'll need to calculate this
    # }

    return render(request, 'inventory/item/item_list.html', context)


@login_required
def inventory_item_detail(request, pk):
    """View details of a specific inventory item"""
    item = get_object_or_404(InventoryItem, pk=pk, vendor=request.user.vendor)
    
    # Get all stock lots
    stock_lots = item.stock_lots.all().order_by('-received_date')
    # Calculate metrics
    current_stock = item.get_current_stock()
    monthly_consumption = item.get_monthly_consumption()
    days_remaining = item.days_of_supply_remaining()
    
    stock_value = current_stock * item.unit_cost

    # Recent usage
    recent_usage = ReagentUsage.objects.filter(
        stock_lot__item=item
    ).order_by('-used_at')[:10]
    
    context = {
        'item': item,
        'stock_lots': stock_lots,
        'current_stock': current_stock,
        'monthly_consumption': monthly_consumption,
        'days_remaining': days_remaining,
        'recent_usage': recent_usage,
        'stock_value': stock_value,  # current_stock * item.unit_cost
    }
    
    return render(request, 'inventory/item/item_detail.html', context)


@login_required
def inventory_item_create(request):
    """Create a new inventory item"""
    if request.method == 'POST':
        form = InventoryItemForm(request.POST)
        if form.is_valid():
            item = form.save(commit=False)
            item.vendor = request.user.vendor
            item.save()
            form.save_m2m()  # Save many-to-many relationships
            messages.success(request, f'Inventory item "{item.name}" created successfully.')
            return redirect('inventory:item_detail', pk=item.pk)
    else:
        form = InventoryItemForm()
    
    context = {'form': form, 'title': 'Add Inventory Item'}
    return render(request, 'inventory/item/item_form.html', context)


@login_required
def inventory_item_update(request, pk):
    """Update an inventory item"""
    item = get_object_or_404(InventoryItem, pk=pk, vendor=request.user.vendor)
    
    if request.method == 'POST':
        form = InventoryItemForm(request.POST, instance=item)
        if form.is_valid():
            form.save()
            messages.success(request, f'Inventory item "{item.name}" updated successfully.')
            return redirect('inventory:item_detail', pk=item.pk)
    else:
        form = InventoryItemForm(instance=item)
    
    context = {'form': form, 'title': 'Edit Inventory Item', 'item': item}
    return render(request, 'inventory/item/item_form.html', context)


@login_required
def inventory_item_delete(request, pk):
    """Delete an inventory item"""
    item = get_object_or_404(InventoryItem, pk=pk, vendor=request.user.vendor)
    
    if request.method == 'POST':
        item_name = item.name
        item.delete()
        messages.success(request, f'Inventory item "{item_name}" deleted successfully.')
        return redirect('inventory:item_list')
    
    context = {'item': item}
    return render(request, 'inventory/item/confirm_delete.html', context)


# ==========================================
# STOCK LOT MANAGEMENT VIEWS
# ==========================================

@login_required
def stock_lot_list(request):
    """List all stock lots with filters"""
    vendor = request.user.vendor
    form = StockLotSearchForm(request.GET)
    
    lots = StockLot.objects.filter(
        item__vendor=vendor
    ).select_related('item', 'received_by')
    
    # Apply filters
    if form.is_valid():
        item = form.cleaned_data.get('item')
        status = form.cleaned_data.get('status')
        expiry_range = form.cleaned_data.get('expiry_range')
        
        if item:
            lots = lots.filter(item=item)
        
        if status:
            lots = lots.filter(status=status)
        
        if expiry_range:
            today = timezone.now().date()
            if expiry_range == 'expired':
                lots = lots.filter(expiry_date__lte=today)
            else:
                days = int(expiry_range)
                lots = lots.filter(
                    expiry_date__lte=today + timedelta(days=days),
                    expiry_date__gt=today
                )
    
    # Add computed fields for template
    lots_with_stats = []
    for lot in lots:
        lots_with_stats.append({
            'lot': lot,
            'days_to_expiry': lot.days_until_expiry(),
            'percentage_remaining': (lot.quantity_remaining / lot.quantity_received * 100) 
                                   if lot.quantity_received > 0 else 0,
            'has_usage': lot.usage_records.exists(),
        })
    
    # Pagination
    paginator = Paginator(lots_with_stats, 25)
    page_number = request.GET.get('page')
    lots_page = paginator.get_page(page_number)
    
    # Statistics
    total_lots = lots.count()
    expired_count = lots.filter(expiry_date__lte=timezone.now().date()).count()
    expiring_soon_count = lots.filter(
        expiry_date__lte=timezone.now().date() + timedelta(days=30),
        expiry_date__gt=timezone.now().date()
    ).count()
    
    context = {
        'lots': lots_page,
        'form': form,
        'total_lots': total_lots,
        'expired_count': expired_count,
        'expiring_soon_count': expiring_soon_count,
    }
    
    return render(request, 'inventory/lot/lot_list.html', context)


@login_required
@vendor_staff_required
def stock_lot_create(request, item_id=None):
    """Receive new stock"""
    if request.method == 'POST':
        form = StockLotForm(request.POST)
        if form.is_valid():
            lot = form.save(commit=False)
            lot.received_by = request.user
            lot.quantity_remaining = lot.quantity_received
            lot.save()
            
            messages.success(
                request, 
                f'Stock lot "{lot.lot_number}" received successfully. '
                f'{lot.quantity_received} units added to inventory.'
            )
            return redirect('inventory:lot_detail', pk=lot.pk)
    else:
        initial = {}
        if item_id:
            item = get_object_or_404(InventoryItem, pk=item_id, vendor=request.user.vendor)
            initial['item'] = item
            initial['unit_cost'] = item.unit_cost
        form = StockLotForm(initial=initial)
        
        # Filter items to only show those from this vendor
        form.fields['item'].queryset = InventoryItem.objects.filter(
            vendor=request.user.vendor,
            is_active=True
        )
    
    context = {
        'form': form, 
        'title': 'Receive Stock',
        'submit_text': 'Receive Stock'
    }
    return render(request, 'inventory/lot/lot_form.html', context)


@login_required
def stock_lot_detail(request, pk):
    """View details of a stock lot"""
    lot = get_object_or_404(
        StockLot.objects.select_related('item', 'received_by'), 
        pk=pk, 
        item__vendor=request.user.vendor
    )
    
    # Get usage history with related data
    usage_history = lot.usage_records.select_related(
        'used_by', 'test_assignment', 'qc_result'
    ).order_by('-used_at')
    
    # Get adjustments
    adjustments = lot.adjustments.select_related('adjusted_by').order_by('-adjusted_at')
    
    # Calculate statistics
    total_used = lot.usage_records.aggregate(
        total=Sum('quantity_used')
    )['total'] or 0
    
    total_adjusted = lot.adjustments.aggregate(
        total=Sum('quantity_adjusted')
    )['total'] or 0
    
    # Usage by type
    usage_by_type = lot.usage_records.values('usage_type').annotate(
        total=Sum('quantity_used')
    ).order_by('-total')
    
    context = {
        'lot': lot,
        'usage_history': usage_history,
        'adjustments': adjustments,
        'total_used': total_used,
        'total_adjusted': total_adjusted,
        'usage_by_type': usage_by_type,
        'days_until_expiry': lot.days_until_expiry(),
        'percentage_remaining': (lot.quantity_remaining / lot.quantity_received * 100) 
                               if lot.quantity_received > 0 else 0,
    }
    
    return render(request, 'inventory/lot/lot_detail.html', context)


@login_required
@vendor_staff_required  # Staff and above can edit
def stock_lot_update(request, pk):
    """Update a stock lot"""
    lot = get_object_or_404(StockLot, pk=pk, item__vendor=request.user.vendor)
    
    if request.method == 'POST':
        form = StockLotForm(request.POST, instance=lot)
        if form.is_valid():
            form.save()
            messages.success(request, f'Stock lot "{lot.lot_number}" updated successfully.')
            return redirect('inventory:lot_detail', pk=lot.pk)
    else:
        form = StockLotForm(instance=lot)
        
        # Filter items to only show those from this vendor
        form.fields['item'].queryset = InventoryItem.objects.filter(
            vendor=request.user.vendor,
            is_active=True
        )
    
    context = {
        'form': form, 
        'title': 'Edit Stock Lot', 
        'lot': lot,
        'submit_text': 'Update Stock Lot'
    }
    return render(request, 'inventory/lot/lot_form.html', context)


@login_required
@vendor_admin_required  # Only admins can delete
@require_POST
def stock_lot_delete(request, pk):
    """
    Delete a stock lot via AJAX
    Only allowed if no usage records exist
    """
    try:
        lot = get_object_or_404(StockLot, pk=pk, item__vendor=request.user.vendor)
        
        # Check if lot has usage records
        usage_count = lot.usage_records.count()
        adjustment_count = lot.adjustments.count()
        
        if usage_count > 0 or adjustment_count > 0:
            return JsonResponse({
                'success': False,
                'error': f'Cannot delete this lot. It has {usage_count} usage record(s) '
                        f'and {adjustment_count} adjustment(s).',
                'usage_count': usage_count,
                'adjustment_count': adjustment_count,
            }, status=400)
        
        # Check if lot has remaining quantity
        if lot.quantity_remaining > 0:
            return JsonResponse({
                'success': False,
                'error': f'Cannot delete this lot. It still has {lot.quantity_remaining} units remaining. '
                        'Please adjust stock to zero first or mark as depleted.',
                'quantity_remaining': lot.quantity_remaining,
            }, status=400)
        
        # Safe to delete
        lot_number = lot.lot_number
        item_name = lot.item.name
        
        with transaction.atomic():
            lot.delete()
        
        return JsonResponse({
            'success': True,
            'message': f'Stock lot "{lot_number}" for {item_name} deleted successfully.',
            'redirect_url': reverse('inventory:lot_list')
        })
        
    except StockLot.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Stock lot not found.'
        }, status=404)
    
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'An error occurred: {str(e)}'
        }, status=500)


@login_required
def stock_lot_mark_expired(request, pk):
    """Mark a stock lot as expired (can be AJAX or regular request)"""
    lot = get_object_or_404(StockLot, pk=pk, item__vendor=request.user.vendor)
    
    if request.method == 'POST':
        lot.status = 'EXPIRED'
        lot.is_available = False
        lot.save()
        
        message = f'Stock lot "{lot.lot_number}" marked as expired.'
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': True,
                'message': message,
                'status': lot.get_status_display(),
            })
        else:
            messages.success(request, message)
            return redirect('inventory:lot_detail', pk=lot.pk)
    
    # GET request - show confirmation
    context = {'lot': lot}
    return render(request, 'inventory/lot/lot_mark_expired.html', context)


@login_required
@require_POST
def stock_lot_quick_adjust(request, pk):
    """Quick stock adjustment via AJAX"""
    try:
        lot = get_object_or_404(StockLot, pk=pk, item__vendor=request.user.vendor)
        
        adjustment_type = request.POST.get('adjustment_type')  # 'add' or 'remove'
        quantity = int(request.POST.get('quantity', 0))
        reason = request.POST.get('reason', 'Quick Adjustment')
        
        if quantity <= 0:
            return JsonResponse({
                'success': False,
                'error': 'Quantity must be greater than zero.'
            }, status=400)
        
        # Determine adjustment amount
        if adjustment_type == 'remove':
            if quantity > lot.quantity_remaining:
                return JsonResponse({
                    'success': False,
                    'error': f'Cannot remove {quantity} units. Only {lot.quantity_remaining} available.'
                }, status=400)
            quantity_adjusted = -quantity
        else:  # add
            quantity_adjusted = quantity
        
        # Create adjustment record
        adjustment = StockAdjustment.objects.create(
            stock_lot=lot,
            quantity_adjusted=quantity_adjusted,
            reason='CORRECTION',
            notes=reason,
            adjusted_by=request.user
        )
        
        # Refresh lot from database
        lot.refresh_from_db()
        
        return JsonResponse({
            'success': True,
            'message': f'Stock adjusted by {quantity_adjusted} units.',
            'new_quantity': lot.quantity_remaining,
            'adjustment_id': adjustment.id,
        })
        
    except ValueError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid quantity value.'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Error: {str(e)}'
        }, status=500)


# ==========================================
# STOCK ADJUSTMENTS
# ==========================================

# @login_required
# def stock_adjustment_create(request):
#     """Make stock adjustment"""
#     if request.method == 'POST':
#         form = StockAdjustmentForm(request.POST)
#         if form.is_valid():
#             adjustment = form.save(commit=False)
#             adjustment.adjusted_by = request.user
#             adjustment.save()
#             messages.success(request, 'Stock adjustment recorded successfully.')
#             return redirect('inventory:lot_detail', pk=adjustment.stock_lot.pk)
#     else:
#         form = StockAdjustmentForm()
    
#     context = {'form': form, 'title': 'Adjust Stock'}
#     return render(request, 'inventory/adjustment_form.html', context)


# ==========================================
# REAGENT USAGE
# ==========================================

@login_required
def reagent_usage_create(request):
    """Record reagent usage"""
    if request.method == 'POST':
        form = ReagentUsageForm(request.POST)
        if form.is_valid():
            usage = form.save(commit=False)
            usage.used_by = request.user
            usage.save()
            messages.success(request, 'Reagent usage recorded successfully.')
            return redirect('inventory:dashboard')
    else:
        form = ReagentUsageForm()
    
    context = {'form': form, 'title': 'Record Reagent Usage'}
    return render(request, 'inventory/reagent/usage_form.html', context)


@login_required
@vendor_admin_required
@require_POST
def reagent_usage_delete(request, pk):
    """
    Delete a reagent usage record via AJAX
    Note: This will NOT restore the stock - manual adjustment needed
    """
    try:
        usage = get_object_or_404(ReagentUsage, pk=pk, stock_lot__item__vendor=request.user.vendor)
        
        # Store info before deletion
        item_name = usage.stock_lot.item.name
        quantity = usage.quantity_used
        
        # Warning about stock not being restored
        warning_message = (
            f'Usage record deleted for {quantity} units of {item_name}. '
            'Note: Stock quantity was NOT automatically restored. '
            'Please create a manual adjustment if needed.'
        )
        
        with transaction.atomic():
            usage.delete()
        
        return JsonResponse({
            'success': True,
            'message': 'Usage record deleted successfully.',
            'warning': warning_message,
            'redirect_url': reverse('inventory:dashboard')
        })
        
    except ReagentUsage.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Usage record not found.'
        }, status=404)
    
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'An error occurred: {str(e)}'
        }, status=500)


# ==========================================
# PURCHASE ORDERS
# ==========================================

@login_required
def purchase_order_list(request):
    """List all purchase orders"""
    vendor = request.user.vendor
    
    pos = PurchaseOrder.objects.filter(vendor=vendor).order_by('-order_date')
    
    # Pagination
    paginator = Paginator(pos, 25)
    page_number = request.GET.get('page')
    pos_page = paginator.get_page(page_number)
    
    context = {'purchase_orders': pos_page}
    return render(request, 'inventory/purchase/po_list.html', context)


@login_required
def purchase_order_detail(request, pk):
    """View purchase order details"""
    po = get_object_or_404(PurchaseOrder, pk=pk, vendor=request.user.vendor)
    
    context = {'po': po}
    return render(request, 'inventory/purchase/po_detail.html', context)


@login_required
@vendor_staff_required # limit to the manager...
def purchase_order_create(request):
    """Create new purchase order"""
    if request.method == 'POST':
        form = PurchaseOrderForm(request.POST)
        formset = PurchaseOrderItemFormSet(request.POST)
        
        if form.is_valid() and formset.is_valid():
            po = form.save(commit=False)
            po.vendor = request.user.vendor
            po.created_by = request.user
            po.save()
            
            # Save items and calculate totals
            subtotal = 0
            for item_form in formset:
                if item_form.cleaned_data and not item_form.cleaned_data.get('DELETE'):
                    item = item_form.save(commit=False)
                    item.purchase_order = po
                    item.save()
                    subtotal += item.total_price
            
            # Update PO totals
            po.subtotal = subtotal
            po.total = subtotal + po.tax + po.shipping
            po.save()
            
            messages.success(request, f'Purchase order "{po.po_number}" created successfully.')
            return redirect('inventory:po_detail', pk=po.pk)
    else:
        form = PurchaseOrderForm()
        formset = PurchaseOrderItemFormSet()
    
    context = {
        'form': form,
        'formset': formset,
        'title': 'Create Purchase Order'
    }
    return render(request, 'inventory/purchase/po_form.html', context)


@login_required
def purchase_order_update(request, pk):
    """Update purchase order"""
    po = get_object_or_404(PurchaseOrder, pk=pk, vendor=request.user.vendor)
    
    if request.method == 'POST':
        form = PurchaseOrderForm(request.POST, instance=po)
        formset = PurchaseOrderItemFormSet(request.POST, instance=po)
        
        if form.is_valid() and formset.is_valid():
            form.save()
            
            # Save items and recalculate totals
            subtotal = 0
            for item_form in formset:
                if item_form.cleaned_data and not item_form.cleaned_data.get('DELETE'):
                    item = item_form.save()
                    subtotal += item.total_price
            
            # Update PO totals
            po.subtotal = subtotal
            po.total = subtotal + po.tax + po.shipping
            po.save()
            
            messages.success(request, f'Purchase order "{po.po_number}" updated successfully.')
            return redirect('inventory:po_detail', pk=po.pk)
    else:
        form = PurchaseOrderForm(instance=po)
        formset = PurchaseOrderItemFormSet(instance=po)
    
    context = {
        'form': form,
        'formset': formset,
        'title': 'Edit Purchase Order',
        'po': po
    }
    return render(request, 'inventory/purchase/po_form.html', context)


@login_required
@vendor_admin_required  # Only admins can delete
@require_POST
def purchase_order_delete(request, pk):
    """
    Delete a purchase order via AJAX
    Only allowed for DRAFT status POs
    """
    try:
        po = get_object_or_404(PurchaseOrder, pk=pk, vendor=request.user.vendor)
        
        # Check if PO can be deleted
        if po.status != 'DRAFT':
            return JsonResponse({
                'success': False,
                'error': f'Cannot delete purchase order with status "{po.get_status_display()}". '
                        'Only DRAFT purchase orders can be deleted.',
                'status': po.status,
            }, status=400)
        
        # Check if any items have been received
        received_items = po.items.filter(quantity_received__gt=0).count()
        if received_items > 0:
            return JsonResponse({
                'success': False,
                'error': f'Cannot delete this purchase order. {received_items} item(s) have been received. '
                        'Please adjust inventory first.',
                'received_items': received_items,
            }, status=400)
        
        # Safe to delete
        po_number = po.po_number
        supplier = po.supplier
        
        with transaction.atomic():
            # Delete related items first
            po.items.all().delete()
            # Delete the PO
            po.delete()
        
        return JsonResponse({
            'success': True,
            'message': f'Purchase order "{po_number}" for supplier "{supplier}" deleted successfully.',
            'redirect_url': reverse('inventory:po_list')
        })
        
    except PurchaseOrder.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Purchase order not found.'
        }, status=404)
    
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'An error occurred: {str(e)}'
        }, status=500)


# ==========================================
# STORAGE MANAGEMENT
# ==========================================

@login_required
def storage_unit_list(request):
    """List all storage units"""
    vendor = request.user.vendor
    units = StorageUnit.objects.filter(vendor=vendor)
    
    context = {'units': units}
    return render(request, 'inventory/storage_unit_list.html', context)


@login_required
def storage_unit_detail(request, pk):
    """View storage unit details and map"""
    unit = get_object_or_404(StorageUnit, pk=pk, vendor=request.user.vendor)
    
    # Get all locations
    locations = unit.locations.all()
    
    # Calculate occupancy
    total_locations = locations.count()
    occupied = locations.filter(is_occupied=True).count()
    occupancy_rate = (occupied / total_locations * 100) if total_locations > 0 else 0
    
    context = {
        'unit': unit,
        'locations': locations,
        'total_locations': total_locations,
        'occupied': occupied,
        'available': total_locations - occupied,
        'occupancy_rate': occupancy_rate,
    }
    return render(request, 'inventory/storage_unit_detail.html', context)


@login_required
def stored_sample_list(request):
    """List all stored samples"""
    vendor = request.user.vendor
    
    samples = StoredSample.objects.filter(
        test_request__vendor=vendor
    ).select_related('storage_location__storage_unit')
    
    # Pagination
    paginator = Paginator(samples, 25)
    page_number = request.GET.get('page')
    samples_page = paginator.get_page(page_number)
    
    context = {'samples': samples_page}
    return render(request, 'inventory/sample_list.html', context)


@login_required
def stored_sample_create(request):
    """Store a sample"""
    if request.method == 'POST':
        form = StoredSampleForm(request.POST)
        if form.is_valid():
            sample = form.save(commit=False)
            sample.stored_by = request.user
            sample.save()
            messages.success(request, f'Sample "{sample.sample_id}" stored successfully.')
            return redirect('inventory:sample_list')
    else:
        form = StoredSampleForm()
    
    context = {'form': form, 'title': 'Store Sample'}
    return render(request, 'inventory/sample_form.html', context)


@login_required
def stored_sample_retrieve(request, pk):
    """Retrieve a stored sample"""
    sample = get_object_or_404(StoredSample, pk=pk, test_request__vendor=request.user.vendor)
    
    if request.method == 'POST':
        form = StoredSampleRetrievalForm(request.POST)
        if form.is_valid():
            sample.status = 'RETRIEVED'
            sample.retrieved_date = timezone.now()
            sample.retrieved_by = request.user
            sample.retrieval_reason = form.cleaned_data['retrieval_reason']
            sample.save()
            messages.success(request, f'Sample "{sample.sample_id}" retrieved successfully.')
            return redirect('inventory:sample_list')
    else:
        form = StoredSampleRetrievalForm()
    
    context = {'form': form, 'sample': sample}
    return render(request, 'inventory/sample_retrieve.html', context)


# ==========================================
# REPORTS & EXPORTS
# ==========================================

@login_required
def inventory_report(request):
    """Generate inventory report"""
    vendor = request.user.vendor
    
    items = InventoryItem.objects.filter(vendor=vendor, is_active=True)
    
    report_data = []
    for item in items:
        current_stock = item.get_current_stock()
        monthly_consumption = item.get_monthly_consumption()
        
        report_data.append({
            'item': item,
            'current_stock': current_stock,
            'monthly_consumption': monthly_consumption,
            'status': 'Low Stock' if item.is_below_reorder_level() else 'OK',
        })
    
    context = {'report_data': report_data}
    return render(request, 'inventory/report.html', context)


@login_required
def export_inventory_csv(request):
    """Export inventory to CSV"""
    vendor = request.user.vendor
    items = InventoryItem.objects.filter(vendor=vendor, is_active=True)
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="inventory_export.csv"'
    
    writer = csv.writer(response)
    writer.writerow([
        'Item Code', 'Name', 'Category', 'Current Stock',
        'Unit of Measure', 'Reorder Level', 'Unit Cost'
    ])
    
    for item in items:
        writer.writerow([
            item.item_code,
            item.name,
            item.category.name,
            item.get_current_stock(),
            item.unit_of_measure,
            item.reorder_level,
            item.unit_cost,
        ])
    
    return response
