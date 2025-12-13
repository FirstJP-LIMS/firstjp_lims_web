from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Sum, F, Count, ExpressionWrapper, DecimalField
from django.utils import timezone
from django.http import JsonResponse, HttpResponse
from django.core.paginator import Paginator
from datetime import timedelta
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
    
    return render(request, 'laboratory/inventory/dashboard.html', context)


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
    
    return render(request, 'laboratory/inventory/item/list.html', context)


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
    }
    
    return render(request, 'inventory/item_detail.html', context)


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
    return render(request, 'laboratory/inventory/item/form.html', context)


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
    return render(request, 'laboratory/inventory/item/form.html', context)


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
    return render(request, 'inventory/item_confirm_delete.html', context)


# ==========================================
# STOCK LOTS
# ==========================================

@login_required
def stock_lot_list(request):
    """List all stock lots with filters"""
    vendor = request.user.vendor
    form = StockLotSearchForm(request.GET)
    
    lots = StockLot.objects.filter(
        item__vendor=vendor
    ).select_related('item')
    
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
    
    # Pagination
    paginator = Paginator(lots, 25)
    page_number = request.GET.get('page')
    lots_page = paginator.get_page(page_number)
    
    context = {
        'lots': lots_page,
        'form': form,
    }
    
    return render(request, 'inventory/lot_list.html', context)


@login_required
def stock_lot_create(request, item_id=None):
    """Receive new stock"""
    if request.method == 'POST':
        form = StockLotForm(request.POST)
        if form.is_valid():
            form.initial['user'] = request.user
            lot = form.save()
            messages.success(request, f'Stock lot "{lot.lot_number}" received successfully.')
            return redirect('inventory:lot_detail', pk=lot.pk)
    else:
        initial = {}
        if item_id:
            item = get_object_or_404(InventoryItem, pk=item_id, vendor=request.user.vendor)
            initial['item'] = item
        form = StockLotForm(initial=initial)
    
    context = {'form': form, 'title': 'Receive Stock'}
    return render(request, 'laboratory/inventory/lot/form.html', context)


@login_required
def stock_lot_detail(request, pk):
    """View details of a stock lot"""
    lot = get_object_or_404(StockLot, pk=pk, item__vendor=request.user.vendor)
    
    # Get usage history
    usage_history = lot.usage_records.all().order_by('-used_at')
    
    # Get adjustments
    adjustments = lot.adjustments.all().order_by('-adjusted_at')
    
    context = {
        'lot': lot,
        'usage_history': usage_history,
        'adjustments': adjustments,
    }
    
    return render(request, 'laboratory/inventory/lot/detail.html', context)


@login_required
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
    
    context = {'form': form, 'title': 'Edit Stock Lot', 'lot': lot}
    return render(request, 'laboratory/inventory/lot/form.html', context)


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
    return render(request, 'inventory/usage_form.html', context)


# ==========================================
# STOCK ADJUSTMENTS
# ==========================================

@login_required
def stock_adjustment_create(request):
    """Make stock adjustment"""
    if request.method == 'POST':
        form = StockAdjustmentForm(request.POST)
        if form.is_valid():
            adjustment = form.save(commit=False)
            adjustment.adjusted_by = request.user
            adjustment.save()
            messages.success(request, 'Stock adjustment recorded successfully.')
            return redirect('inventory:lot_detail', pk=adjustment.stock_lot.pk)
    else:
        form = StockAdjustmentForm()
    
    context = {'form': form, 'title': 'Adjust Stock'}
    return render(request, 'inventory/adjustment_form.html', context)


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
    return render(request, 'inventory/po_list.html', context)


@login_required
def purchase_order_detail(request, pk):
    """View purchase order details"""
    po = get_object_or_404(PurchaseOrder, pk=pk, vendor=request.user.vendor)
    
    context = {'po': po}
    return render(request, 'inventory/po_detail.html', context)


@login_required
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
    return render(request, 'laboratory/inventory/purchase/form.html', context)


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
    return render(request, 'laboratory/inventory/purchase/form.html', context)


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
