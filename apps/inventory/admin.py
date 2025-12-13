from django.contrib import admin
from django.utils.html import format_html
from django.db.models import Sum, F
from .models import (
    InventoryCategory, InventoryItem, StockLot, ReagentUsage,
    StockAdjustment, PurchaseOrder, PurchaseOrderItem,
    StorageUnit, StorageLocation, StoredSample
)


# ==========================================
# INVENTORY CATEGORY
# ==========================================

@admin.register(InventoryCategory)
class InventoryCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'category_type', 'vendor', 'item_count']
    list_filter = ['category_type', 'vendor']
    search_fields = ['name', 'description']
    
    def item_count(self, obj):
        return obj.items.count()
    item_count.short_description = 'Items'


# ==========================================
# INVENTORY ITEM
# ==========================================

@admin.register(InventoryItem)
class InventoryItemAdmin(admin.ModelAdmin):
    list_display = [
        'item_code', 'name', 'category', 'manufacturer',
        'current_stock_display', 'reorder_level', 'stock_status',
        'unit_cost', 'is_active'
    ]
    list_filter = [
        'category', 'storage_condition', 'is_active',
        'requires_lot_tracking', 'vendor'
    ]
    search_fields = ['item_code', 'name', 'manufacturer', 'catalog_number']
    readonly_fields = ['created_at', 'updated_at']
    filter_horizontal = ['tests']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('vendor', 'category', 'item_code', 'name', 'manufacturer', 'catalog_number')
        }),
        ('Unit Information', {
            'fields': ('unit_of_measure', 'pack_size', 'unit_cost')
        }),
        ('Storage', {
            'fields': ('storage_condition', 'storage_location')
        }),
        ('Stock Management', {
            'fields': ('reorder_level', 'minimum_stock', 'maximum_stock')
        }),
        ('Tests', {
            'fields': ('tests',),
            'classes': ('collapse',)
        }),
        ('Options', {
            'fields': ('is_active', 'requires_barcode', 'requires_lot_tracking')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def current_stock_display(self, obj):
        current = obj.get_current_stock()
        if current == 0:
            color = 'red'
        elif current <= obj.reorder_level:
            color = 'orange'
        else:
            color = 'green'
        return format_html(
            '<span style="color: {}; font-weight: bold;">{} {}</span>',
            color, current, obj.unit_of_measure
        )
    current_stock_display.short_description = 'Current Stock'
    
    def stock_status(self, obj):
        if obj.is_below_reorder_level():
            return format_html('<span style="color: red;">⚠ Low Stock</span>')
        return format_html('<span style="color: green;">✓ OK</span>')
    stock_status.short_description = 'Status'


# ==========================================
# STOCK LOT
# ==========================================

@admin.register(StockLot)
class StockLotAdmin(admin.ModelAdmin):
    list_display = [
        'item', 'lot_number', 'received_date', 'expiry_date',
        'quantity_display', 'status_display', 'days_to_expiry'
    ]
    list_filter = ['status', 'expiry_date', 'received_date', 'item__vendor']
    search_fields = ['lot_number', 'barcode', 'item__name', 'item__item_code']
    readonly_fields = ['total_cost', 'created_at', 'updated_at']
    date_hierarchy = 'received_date'
    
    fieldsets = (
        ('Item & Lot', {
            'fields': ('item', 'lot_number', 'barcode')
        }),
        ('Quantity', {
            'fields': ('quantity_received', 'quantity_remaining')
        }),
        ('Dates', {
            'fields': ('received_date', 'manufacture_date', 'expiry_date', 'opened_date')
        }),
        ('Storage', {
            'fields': ('storage_location',)
        }),
        ('Purchase Info', {
            'fields': ('supplier', 'purchase_order', 'unit_cost', 'total_cost')
        }),
        ('Status', {
            'fields': ('status', 'is_available', 'received_by', 'notes')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def quantity_display(self, obj):
        percentage = (obj.quantity_remaining / obj.quantity_received * 100) if obj.quantity_received > 0 else 0
        return format_html(
            '{} / {} ({:.0f}%)',
            obj.quantity_remaining, obj.quantity_received, percentage
        )
    quantity_display.short_description = 'Quantity (Remaining/Total)'
    
    def status_display(self, obj):
        colors = {
            'AVAILABLE': 'green',
            'IN_USE': 'blue',
            'QUARANTINE': 'orange',
            'EXPIRED': 'red',
            'DEPLETED': 'gray',
        }
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            colors.get(obj.status, 'black'), obj.get_status_display()
        )
    status_display.short_description = 'Status'
    
    def days_to_expiry(self, obj):
        days = obj.days_until_expiry()
        if days is None:
            return '—'
        if days < 0:
            return format_html('<span style="color: red;">Expired</span>')
        elif days <= 7:
            return format_html('<span style="color: red;">{} days</span>', days)
        elif days <= 30:
            return format_html('<span style="color: orange;">{} days</span>', days)
        else:
            return f'{days} days'
    days_to_expiry.short_description = 'Days to Expiry'


# ==========================================
# REAGENT USAGE
# ==========================================

@admin.register(ReagentUsage)
class ReagentUsageAdmin(admin.ModelAdmin):
    list_display = [
        'stock_lot', 'quantity_used', 'usage_type',
        'used_at', 'used_by'
    ]
    list_filter = ['usage_type', 'used_at', 'stock_lot__item__vendor']
    search_fields = ['stock_lot__lot_number', 'stock_lot__item__name', 'notes']
    date_hierarchy = 'used_at'
    readonly_fields = ['used_at']
    
    fieldsets = (
        (None, {
            'fields': ('stock_lot', 'quantity_used', 'usage_type')
        }),
        ('Linked Records', {
            'fields': ('test_assignment', 'qc_result', 'calibration'),
            'classes': ('collapse',)
        }),
        ('Details', {
            'fields': ('used_at', 'used_by', 'notes')
        }),
    )


# ==========================================
# STOCK ADJUSTMENT
# ==========================================

@admin.register(StockAdjustment)
class StockAdjustmentAdmin(admin.ModelAdmin):
    list_display = [
        'stock_lot', 'quantity_adjusted', 'reason',
        'adjusted_at', 'adjusted_by'
    ]
    list_filter = ['reason', 'adjusted_at']
    search_fields = ['stock_lot__lot_number', 'notes']
    date_hierarchy = 'adjusted_at'
    readonly_fields = ['adjusted_at']


# ==========================================
# PURCHASE ORDER
# ==========================================

class PurchaseOrderItemInline(admin.TabularInline):
    model = PurchaseOrderItem
    extra = 1
    readonly_fields = ['total_price']
    fields = ['inventory_item', 'quantity_ordered', 'quantity_received', 'unit_price', 'total_price']


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = [
        'po_number', 'supplier', 'status',
        'order_date', 'expected_delivery', 'total_display'
    ]
    list_filter = ['status', 'order_date', 'vendor']
    search_fields = ['po_number', 'supplier']
    date_hierarchy = 'order_date'
    readonly_fields = ['created_at', 'updated_at', 'created_by']
    inlines = [PurchaseOrderItemInline]
    
    fieldsets = (
        ('Basic Info', {
            'fields': ('vendor', 'po_number', 'supplier', 'status')
        }),
        ('Dates', {
            'fields': ('order_date', 'expected_delivery', 'actual_delivery')
        }),
        ('Financial', {
            'fields': ('subtotal', 'tax', 'shipping', 'total')
        }),
        ('Notes', {
            'fields': ('notes',)
        }),
        ('Metadata', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def total_display(self, obj):
        return f'₦{obj.total:,.2f}'
    total_display.short_description = 'Total'
    
    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


# ==========================================
# STORAGE MANAGEMENT
# ==========================================

@admin.register(StorageUnit)
class StorageUnitAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'unit_type', 'location',
        'capacity_display', 'temperature_display', 'is_active'
    ]
    list_filter = ['unit_type', 'is_active', 'vendor']
    search_fields = ['name', 'location']
    
    def capacity_display(self, obj):
        total = obj.total_shelves * obj.total_racks * obj.total_boxes
        return f'{total} positions'
    capacity_display.short_description = 'Capacity'
    
    def temperature_display(self, obj):
        if obj.current_temperature:
            diff = abs(obj.current_temperature - obj.target_temperature)
            if diff > 2:
                color = 'red'
            elif diff > 1:
                color = 'orange'
            else:
                color = 'green'
            return format_html(
                '<span style="color: {};">{:.1f}°C (Target: {:.1f}°C)</span>',
                color, obj.current_temperature, obj.target_temperature
            )
        return f'Target: {obj.target_temperature}°C'
    temperature_display.short_description = 'Temperature'


class StorageLocationInline(admin.TabularInline):
    model = StorageLocation
    extra = 0
    readonly_fields = ['location_code', 'is_occupied']
    fields = ['shelf_number', 'rack_number', 'box_number', 'position', 'location_code', 'is_occupied']


@admin.register(StorageLocation)
class StorageLocationAdmin(admin.ModelAdmin):
    list_display = [
        'location_code', 'storage_unit', 'shelf_number',
        'rack_number', 'box_number', 'position', 'occupancy_status'
    ]
    list_filter = ['storage_unit', 'is_occupied']
    search_fields = ['location_code']
    readonly_fields = ['location_code']
    
    def occupancy_status(self, obj):
        if obj.is_occupied:
            return format_html('<span style="color: red;">● Occupied</span>')
        return format_html('<span style="color: green;">○ Available</span>')
    occupancy_status.short_description = 'Status'


@admin.register(StoredSample)
class StoredSampleAdmin(admin.ModelAdmin):
    list_display = [
        'sample_id', 'sample_type', 'storage_location',
        'stored_date', 'disposal_date', 'status_display'
    ]
    list_filter = ['status', 'sample_type', 'stored_date']
    search_fields = ['sample_id', 'test_request__request_number']
    date_hierarchy = 'stored_date'
    readonly_fields = ['stored_date', 'disposal_date']
    
    fieldsets = (
        ('Sample Info', {
            'fields': ('test_request', 'sample_id', 'sample_type')
        }),
        ('Storage', {
            'fields': ('storage_location', 'stored_date', 'stored_by')
        }),
        ('Retention', {
            'fields': ('retention_days', 'disposal_date', 'status')
        }),
        ('Retrieval', {
            'fields': ('retrieved_date', 'retrieved_by', 'retrieval_reason'),
            'classes': ('collapse',)
        }),
        ('Notes', {
            'fields': ('notes',)
        }),
    )
    
    def status_display(self, obj):
        colors = {
            'STORED': 'green',
            'RETRIEVED': 'blue',
            'DISPOSED': 'gray',
        }
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            colors.get(obj.status, 'black'), obj.get_status_display()
        )
    status_display.short_description = 'Status'


# ==========================================
# ADMIN ACTIONS
# ==========================================

def mark_lots_as_expired(modeladmin, request, queryset):
    """Mark selected lots as expired"""
    updated = queryset.update(status='EXPIRED', is_available=False)
    modeladmin.message_user(request, f'{updated} lot(s) marked as expired.')
mark_lots_as_expired.short_description = 'Mark selected lots as expired'

def reactivate_items(modeladmin, request, queryset):
    """Reactivate selected items"""
    updated = queryset.update(is_active=True)
    modeladmin.message_user(request, f'{updated} item(s) reactivated.')
reactivate_items.short_description = 'Reactivate selected items'

# Add actions to respective admins
StockLotAdmin.actions = [mark_lots_as_expired]
InventoryItemAdmin.actions = [reactivate_items]