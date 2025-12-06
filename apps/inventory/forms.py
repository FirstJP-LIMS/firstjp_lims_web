from django import forms
from .models import (
    InventoryItem, StockLot, ReagentUsage, 
    PurchaseOrder, PurchaseOrderItem, StockAdjustment
)


class InventoryItemForm(forms.ModelForm):
    class Meta:
        model = InventoryItem
        fields = [
            'category', 'item_code', 'name', 'manufacturer', 
            'catalog_number', 'unit_of_measure', 'pack_size',
            'storage_condition', 'storage_location',
            'reorder_level', 'minimum_stock', 'maximum_stock',
            'unit_cost', 'tests', 'is_active'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input'}),
            'item_code': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'RGT-001'}),
            'unit_cost': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.01'}),
            'tests': forms.CheckboxSelectMultiple(),
        }
    
    def __init__(self, vendor=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if vendor:
            self.fields['category'].queryset = self.fields['category'].queryset.filter(vendor=vendor)
            self.fields['tests'].queryset = self.fields['tests'].queryset.filter(vendor=vendor)


class StockLotForm(forms.ModelForm):
    class Meta:
        model = StockLot
        fields = [
            'item', 'lot_number', 'barcode',
            'quantity_received', 'manufacture_date', 'expiry_date',
            'storage_location', 'supplier', 'purchase_order',
            'unit_cost', 'notes'
        ]
        widgets = {
            'manufacture_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-input'}),
            'expiry_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-input'}),
            'quantity_received': forms.NumberInput(attrs={'class': 'form-input'}),
            'unit_cost': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.01'}),
            'notes': forms.Textarea(attrs={'rows': 3, 'class': 'form-textarea'}),
        }
    
    def __init__(self, vendor=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if vendor:
            self.fields['item'].queryset = InventoryItem.objects.filter(vendor=vendor)
    
    def clean(self):
        cleaned = super().clean()
        expiry = cleaned.get('expiry_date')
        manufacture = cleaned.get('manufacture_date')
        
        if expiry and manufacture and expiry <= manufacture:
            raise forms.ValidationError('Expiry date must be after manufacture date')
        
        return cleaned


class ReagentUsageForm(forms.ModelForm):
    """Manual reagent usage entry"""
    class Meta:
        model = ReagentUsage
        fields = ['stock_lot', 'quantity_used', 'usage_type', 'notes']
        widgets = {
            'quantity_used': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.01'}),
            'notes': forms.Textarea(attrs={'rows': 2, 'class': 'form-textarea'}),
        }
    
    def __init__(self, vendor=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if vendor:
            # Only show available stock lots
            self.fields['stock_lot'].queryset = StockLot.objects.filter(
                item__vendor=vendor,
                is_available=True,
                quantity_remaining__gt=0
            ).select_related('item')


class StockAdjustmentForm(forms.ModelForm):
    class Meta:
        model = StockAdjustment
        fields = ['stock_lot', 'quantity_adjusted', 'reason', 'notes']
        widgets = {
            'quantity_adjusted': forms.NumberInput(attrs={
                'class': 'form-input',
                'help_text': 'Positive to add, negative to remove'
            }),
            'notes': forms.Textarea(attrs={'rows': 3, 'class': 'form-textarea'}),
        }
    
    def __init__(self, vendor=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if vendor:
            self.fields['stock_lot'].queryset = StockLot.objects.filter(
                item__vendor=vendor
            ).select_related('item')


class PurchaseOrderForm(forms.ModelForm):
    class Meta:
        model = PurchaseOrder
        fields = [
            'po_number', 'supplier', 'order_date', 
            'expected_delivery', 'notes'
        ]
        widgets = {
            'order_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-input'}),
            'expected_delivery': forms.DateInput(attrs={'type': 'date', 'class': 'form-input'}),
            'notes': forms.Textarea(attrs={'rows': 3, 'class': 'form-textarea'}),
        }


class PurchaseOrderItemForm(forms.ModelForm):
    class Meta:
        model = PurchaseOrderItem
        fields = ['inventory_item', 'quantity_ordered', 'unit_price', 'notes']
        widgets = {
            'unit_price': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.01'}),
            'quantity_ordered': forms.NumberInput(attrs={'class': 'form-input'}),
        }
    
    def __init__(self, vendor=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if vendor:
            self.fields['inventory_item'].queryset = InventoryItem.objects.filter(
                vendor=vendor, is_active=True
            )