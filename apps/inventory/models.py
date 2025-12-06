from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.validators import MinValueValidator
from decimal import Decimal


# ==========================================
# 1. REAGENT/CONSUMABLE MASTER
# ==========================================

class InventoryCategory(models.Model):
    """Categories for inventory items"""
    CATEGORY_TYPES = [
        ('REAGENT', 'Reagent'),
        ('CONSUMABLE', 'Consumable'),
        ('CONTROL', 'Quality Control Material'),
        ('CALIBRATOR', 'Calibrator'),
        ('EQUIPMENT', 'Equipment Parts'),
    ]
    
    vendor = models.ForeignKey('tenants.Vendor', on_delete=models.CASCADE, related_name='inventory_categories')
    name = models.CharField(max_length=100)
    category_type = models.CharField(max_length=20, choices=CATEGORY_TYPES)
    description = models.TextField(blank=True)
    
    class Meta:
        unique_together = ('vendor', 'name')
        verbose_name_plural = "Inventory Categories"
    
    def __str__(self):
        return f"{self.name} ({self.get_category_type_display()})"


class InventoryItem(models.Model):
    """
    Master list of reagents/consumables.
    This is the 'catalog' - what items your lab uses.
    """
    STORAGE_CONDITIONS = [
        ('RT', 'Room Temperature (15-25°C)'),
        ('FRIDGE', 'Refrigerated (2-8°C)'),
        ('FREEZER', 'Frozen (-20°C)'),
        ('DEEP_FREEZE', 'Deep Freeze (-80°C)'),
        ('SPECIAL', 'Special Storage'),
    ]
    
    vendor = models.ForeignKey('tenants.Vendor', on_delete=models.CASCADE, related_name='inventory_items')
    category = models.ForeignKey(InventoryCategory, on_delete=models.PROTECT, related_name='items')
    
    # Item Identification
    item_code = models.CharField(max_length=50, unique=True, help_text="Internal item code (e.g., RGT-001)")
    name = models.CharField(max_length=200, help_text="Reagent/Item name")
    manufacturer = models.CharField(max_length=200)
    catalog_number = models.CharField(max_length=100, blank=True, help_text="Manufacturer's catalog/part number")
    
    # Unit Information
    unit_of_measure = models.CharField(max_length=50, default='pcs', help_text="ml, L, tests, pcs, boxes")
    pack_size = models.IntegerField(default=1, help_text="Number of units per pack (e.g., 100 tests/kit)")
    
    # Storage
    storage_condition = models.CharField(max_length=20, choices=STORAGE_CONDITIONS, default='RT')
    storage_location = models.CharField(max_length=100, blank=True, help_text="Shelf/Cabinet location")
    
    # Stock Management
    reorder_level = models.IntegerField(validators=[MinValueValidator(0)], help_text="Alert when stock reaches this level")
    minimum_stock = models.IntegerField(validators=[MinValueValidator(0)], help_text="Minimum stock to maintain")
    maximum_stock = models.IntegerField(validators=[MinValueValidator(0)], help_text="Maximum stock capacity")
    
    # Pricing
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2, help_text="Cost per unit")
    
    # Tests Association (for reagents)
    tests = models.ManyToManyField('labs.VendorTest', blank=True, related_name='required_reagents', help_text="Which tests use this reagent")
    
    # Status
    is_active = models.BooleanField(default=True)
    requires_barcode = models.BooleanField(default=False)
    requires_lot_tracking = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['category', 'name']
        indexes = [
            models.Index(fields=['vendor', 'is_active']),
        ]
    
    def get_current_stock(self):
        """Calculate total available stock across all lots"""
        return self.stock_lots.filter(
            is_available=True
        ).aggregate(
            total=models.Sum('quantity_remaining')
        )['total'] or 0
    
    def is_below_reorder_level(self):
        """Check if stock needs reordering"""
        return self.get_current_stock() <= self.reorder_level
    
    def get_monthly_consumption(self):
        """Calculate average monthly consumption"""
        thirty_days_ago = timezone.now() - timezone.timedelta(days=30)
        consumption = self.usage_records.filter(
            used_at__gte=thirty_days_ago
        ).aggregate(
            total=models.Sum('quantity_used')
        )['total'] or 0
        return consumption
    
    def days_of_supply_remaining(self):
        """Calculate how many days of stock remain"""
        current_stock = self.get_current_stock()
        daily_avg = self.get_monthly_consumption() / 30
        if daily_avg > 0:
            return int(current_stock / daily_avg)
        return None
    
    def __str__(self):
        return f"{self.item_code} - {self.name}"


# ==========================================
# 2. STOCK LOT/BATCH TRACKING
# ==========================================

class StockLot(models.Model):
    """
    Individual lots/batches of reagents received.
    Each shipment creates a new StockLot record.
    """
    LOT_STATUS = [
        ('AVAILABLE', 'Available'),
        ('IN_USE', 'In Use'),
        ('QUARANTINE', 'Quarantine'),
        ('EXPIRED', 'Expired'),
        ('DEPLETED', 'Depleted'),
    ]
    
    item = models.ForeignKey(InventoryItem, on_delete=models.CASCADE, related_name='stock_lots')
    
    # Lot Information
    lot_number = models.CharField(max_length=100, help_text="Manufacturer's lot/batch number")
    barcode = models.CharField(max_length=100, blank=True, unique=True, help_text="Internal barcode for scanning")
    
    # Quantity
    quantity_received = models.IntegerField(validators=[MinValueValidator(1)])
    quantity_remaining = models.IntegerField(validators=[MinValueValidator(0)])
    
    # Dates
    received_date = models.DateField(default=timezone.now)
    manufacture_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(db_index=True)
    opened_date = models.DateField(null=True, blank=True,help_text="Date vial/bottle was first opened")
    
    # Storage Location (for fridge mapping)
    storage_location = models.CharField(max_length=100, blank=True,
                                        help_text="Freezer A, Shelf 2, Box 3")
    
    # Purchase Information
    supplier = models.CharField(max_length=200)
    purchase_order = models.CharField(max_length=100, blank=True)
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2)
    total_cost = models.DecimalField(max_digits=12, decimal_places=2)
    
    # Status
    status = models.CharField(max_length=20, choices=LOT_STATUS, default='AVAILABLE')
    is_available = models.BooleanField(default=True)
    
    # Documentation
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='received_lots')
    notes = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['expiry_date', '-received_date']
        unique_together = ('item', 'lot_number')
        indexes = [
            models.Index(fields=['expiry_date', 'is_available']),
        ]
    
    def save(self, *args, **kwargs):
        """Calculate total cost and check expiry"""
        self.total_cost = self.quantity_received * self.unit_cost
        
        # Auto-update status based on expiry
        if self.expiry_date <= timezone.now().date():
            self.status = 'EXPIRED'
            self.is_available = False
        
        # Auto-update status based on quantity
        if self.quantity_remaining == 0:
            self.status = 'DEPLETED'
            self.is_available = False
        
        super().save(*args, **kwargs)
    
    def days_until_expiry(self):
        """Days remaining until expiry"""
        if not self.expiry_date:
            return None
        delta = self.expiry_date - timezone.now().date()
        return delta.days
    
    def is_expired(self):
        """Check if lot is expired"""
        return self.expiry_date <= timezone.now().date()
    
    def is_expiring_soon(self, days=30):
        """Check if lot expires within specified days"""
        return 0 < self.days_until_expiry() <= days
    
    def __str__(self):
        return f"{self.item.item_code} - Lot {self.lot_number} (Exp: {self.expiry_date})"


# ==========================================
# 3. USAGE TRACKING
# ==========================================

class ReagentUsage(models.Model):
    """
    Track reagent consumption per test.
    Links inventory to actual test requests.
    """
    stock_lot = models.ForeignKey(StockLot, on_delete=models.CASCADE, related_name='usage_records')
    
    # What was used
    quantity_used = models.DecimalField(max_digits=10, decimal_places=2,
                                        validators=[MinValueValidator(0)])
    
    # Why it was used
    test_assignment = models.ForeignKey('labs.TestAssignment', on_delete=models.SET_NULL, null=True, blank=True,related_name='reagent_usage')
    qc_result = models.ForeignKey('labs.QCResult',  on_delete=models.SET_NULL, null=True, blank=True, related_name='reagent_usage')
    calibration = models.ForeignKey('labs.Equipment',  on_delete=models.SET_NULL, null=True, blank=True,related_name='calibration_usage')
    
    USAGE_TYPE = [
        ('TEST', 'Patient Test'),
        ('QC', 'Quality Control'),
        ('CALIBRATION', 'Calibration'),
        ('MAINTENANCE', 'Maintenance'),
        ('WASTE', 'Waste/Spillage'),
    ]
    usage_type = models.CharField(max_length=20, choices=USAGE_TYPE, default='TEST')
    
    # When
    used_at = models.DateTimeField(default=timezone.now)
    used_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    
    # Notes
    notes = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-used_at']
        indexes = [
            models.Index(fields=['stock_lot', 'used_at']),
        ]
    
    def save(self, *args, **kwargs):
        """Deduct quantity from stock lot"""
        super().save(*args, **kwargs)
        
        # Update stock lot quantity
        self.stock_lot.quantity_remaining -= Decimal(str(self.quantity_used))
        self.stock_lot.save()
    
    def __str__(self):
        return f"{self.stock_lot.item.name} - {self.quantity_used} used on {self.used_at.date()}"


# ==========================================
# 4. STOCK ADJUSTMENTS & TRANSFERS
# ==========================================

class StockAdjustment(models.Model):
    """
    Manual stock adjustments for corrections, damage, etc.
    """
    ADJUSTMENT_REASONS = [
        ('DAMAGE', 'Damaged'),
        ('EXPIRED', 'Expired Disposal'),
        ('CORRECTION', 'Inventory Correction'),
        ('TRANSFER', 'Transfer to Another Lab'),
        ('RETURN', 'Return to Supplier'),
        ('OTHER', 'Other'),
    ]
    
    stock_lot = models.ForeignKey(StockLot, on_delete=models.CASCADE, related_name='adjustments')
    
    quantity_adjusted = models.IntegerField(help_text="Positive = Add, Negative = Remove")
    reason = models.CharField(max_length=20, choices=ADJUSTMENT_REASONS)
    notes = models.TextField()
    
    adjusted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    adjusted_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-adjusted_at']
    
    def save(self, *args, **kwargs):
        """Apply adjustment to stock lot"""
        super().save(*args, **kwargs)
        self.stock_lot.quantity_remaining += self.quantity_adjusted
        self.stock_lot.save()
    
    def __str__(self):
        return f"{self.stock_lot.item.name} - Adjusted by {self.quantity_adjusted}"


# ==========================================
# 5. PURCHASE ORDERS & PROCUREMENT
# ==========================================

class PurchaseOrder(models.Model):
    """
    Track purchase orders for reagents/consumables.
    """
    PO_STATUS = [
        ('DRAFT', 'Draft'),
        ('SUBMITTED', 'Submitted'),
        ('APPROVED', 'Approved'),
        ('ORDERED', 'Ordered'),
        ('PARTIAL', 'Partially Received'),
        ('COMPLETE', 'Complete'),
        ('CANCELLED', 'Cancelled'),
    ]
    
    vendor = models.ForeignKey('tenants.Vendor', on_delete=models.CASCADE, related_name='purchase_orders')
    
    po_number = models.CharField(max_length=50, unique=True)
    supplier = models.CharField(max_length=200)
    
    status = models.CharField(max_length=20, choices=PO_STATUS, default='DRAFT')
    
    order_date = models.DateField(default=timezone.now)
    expected_delivery = models.DateField(null=True, blank=True)
    actual_delivery = models.DateField(null=True, blank=True)
    
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    shipping = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    notes = models.TextField(blank=True)
    
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-order_date']
    
    def __str__(self):
        return f"PO-{self.po_number} - {self.supplier}"


class PurchaseOrderItem(models.Model):
    """Line items in a purchase order"""
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='items')
    inventory_item = models.ForeignKey(InventoryItem, on_delete=models.CASCADE)
    
    quantity_ordered = models.IntegerField(validators=[MinValueValidator(1)])
    quantity_received = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    total_price = models.DecimalField(max_digits=12, decimal_places=2)
    
    notes = models.TextField(blank=True)
    
    def save(self, *args, **kwargs):
        """Calculate total price"""
        self.total_price = self.quantity_ordered * self.unit_price
        super().save(*args, **kwargs)
    
    def is_fully_received(self):
        return self.quantity_received >= self.quantity_ordered
    
    def __str__(self):
        return f"{self.inventory_item.name} x{self.quantity_ordered}"
    

# PART 3: Freezer/Fridge Sample Mapping
# ==========================================
# SAMPLE STORAGE MANAGEMENT
# ==========================================

class StorageUnit(models.Model):
    """
    Physical storage units (Freezers, Fridges, Cabinets).
    """
    UNIT_TYPES = [
        ('FREEZER_-80', 'Ultra-Low Freezer (-80°C)'),
        ('FREEZER_-20', 'Freezer (-20°C)'),
        ('FRIDGE', 'Refrigerator (2-8°C)'),
        ('ROOM_TEMP', 'Room Temperature Storage'),
        ('INCUBATOR', 'Incubator'),
    ]
    
    vendor = models.ForeignKey('tenants.Vendor', on_delete=models.CASCADE, related_name='storage_units')
    
    name = models.CharField(max_length=100, help_text="e.g., 'Freezer A', 'Fridge 2'")
    unit_type = models.CharField(max_length=20, choices=UNIT_TYPES)
    location = models.CharField(max_length=200, help_text="Physical location in lab")
    
    # Capacity
    total_shelves = models.IntegerField(default=1)
    total_racks = models.IntegerField(default=1, help_text="Racks per shelf")
    total_boxes = models.IntegerField(default=1, help_text="Boxes per rack")
    
    # Temperature monitoring
    target_temperature = models.DecimalField(max_digits=5, decimal_places=2, 
                                             help_text="Target temperature in °C")
    current_temperature = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    last_temp_check = models.DateTimeField(null=True, blank=True)
    
    # Status
    is_active = models.BooleanField(default=True)
    
    class Meta:
        unique_together = ('vendor', 'name')
    
    def __str__(self):
        return f"{self.name} ({self.get_unit_type_display()})"


class StorageLocation(models.Model):
    """
    Specific storage locations within a unit.
    Hierarchy: Unit → Shelf → Rack → Box → Position
    """
    storage_unit = models.ForeignKey(StorageUnit, on_delete=models.CASCADE, related_name='locations')
    
    shelf_number = models.IntegerField()
    rack_number = models.IntegerField(default=1)
    box_number = models.IntegerField(default=1)
    position = models.CharField(max_length=10, blank=True, help_text="Position within box (e.g., A1, B3)")
    
    # Full location code
    location_code = models.CharField(max_length=50, unique=True,
                                     help_text="Auto-generated: FRZ-A-S2-R1-B3-A1")
    
    is_occupied = models.BooleanField(default=False)
    
    class Meta:
        unique_together = ('storage_unit', 'shelf_number', 'rack_number', 'box_number', 'position')
        ordering = ['storage_unit', 'shelf_number', 'rack_number', 'box_number', 'position']
    
    def save(self, *args, **kwargs):
        """Auto-generate location code"""
        if not self.location_code:
            unit_code = self.storage_unit.name[:3].upper()
            self.location_code = f"{unit_code}-S{self.shelf_number}-R{self.rack_number}-B{self.box_number}"
            if self.position:
                self.location_code += f"-{self.position}"
        super().save(*args, **kwargs)
    
    def __str__(self):
        return self.location_code


class StoredSample(models.Model):
    """
    Tracks samples stored in freezers/fridges.
    """
    SAMPLE_STATUS = [
        ('STORED', 'Stored'),
        ('RETRIEVED', 'Retrieved'),
        ('DISPOSED', 'Disposed'),
    ]
    
    # Link to original test request
    test_request = models.ForeignKey('labs.TestRequest', on_delete=models.CASCADE, 
                                     related_name='stored_samples')
    
    sample_id = models.CharField(max_length=100, unique=True)
    sample_type = models.CharField(max_length=100, help_text="Serum, Plasma, Whole Blood")
    
    # Storage location
    storage_location = models.ForeignKey(StorageLocation, on_delete=models.PROTECT, 
                                         related_name='stored_samples')
    
    # Storage details
    stored_date = models.DateTimeField(default=timezone.now)
    stored_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    
    # Retention
    retention_days = models.IntegerField(default=30, help_text="Days to keep sample")
    disposal_date = models.DateField(null=True, blank=True)
    
    status = models.CharField(max_length=20, choices=SAMPLE_STATUS, default='STORED')
    
    # Retrieval tracking
    retrieved_date = models.DateTimeField(null=True, blank=True)
    retrieved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, 
                                     null=True, blank=True, related_name='retrieved_samples')
    retrieval_reason = models.TextField(blank=True)
    
    notes = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-stored_date']
        indexes = [
            models.Index(fields=['storage_location', 'status']),
        ]
    
    def save(self, *args, **kwargs):
        """Calculate disposal date and update location occupancy"""
        if not self.disposal_date and self.retention_days:
            self.disposal_date = (self.stored_date + timezone.timedelta(days=self.retention_days)).date()
        
        # Mark location as occupied/free
        if self.status == 'STORED':
            self.storage_location.is_occupied = True
        else:
            self.storage_location.is_occupied = False
        self.storage_location.save()
        
        super().save(*args, **kwargs)
    
    def is_due_for_disposal(self):
        """Check if sample should be disposed"""
        return self.disposal_date and timezone.now().date() >= self.disposal_date
    
    def __str__(self):
        return f"{self.sample_id} - {self.storage_location.location_code}"


"""
## 📊 **Summary: Complete Data Flow**
┌─────────────────────────────────────────────────────────┐
│                   PATIENT REGISTRATION                  │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│  BILLING TYPE SELECTED (Cash/HMO/Corporate)             │
│  → BillingInformation created                           │
│  → Price calculated from PriceList                      │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│  PAYMENT COLLECTED (if Cash) or INVOICE CREATED         │
│  → Payment record                                       │
│  → Invoice record (for HMO/Corporate)                   │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│  TEST PERFORMED                                         │
│  → ReagentUsage recorded (deducts from StockLot)        │
│  → Sample stored (StoredSample)                         │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│  MONTH-END BILLING                                      │
│  → Generate Invoice for HMOs/Corporate                  │
│  → Track InvoicePayments                                │
│  → Generate Reports                                     │
└─────────────────────────────────────────────────────────┘

"""