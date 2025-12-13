# from django import forms
# from .models import (
#     InventoryItem, StockLot, ReagentUsage, 
#     PurchaseOrder, PurchaseOrderItem, StockAdjustment
# )


# class InventoryItemForm(forms.ModelForm):
#     class Meta:
#         model = InventoryItem
#         fields = [
#             'category', 'item_code', 'name', 'manufacturer', 
#             'catalog_number', 'unit_of_measure', 'pack_size',
#             'storage_condition', 'storage_location',
#             'reorder_level', 'minimum_stock', 'maximum_stock',
#             'unit_cost', 'tests', 'is_active'
#         ]
#         widgets = {
#             'name': forms.TextInput(attrs={'class': 'form-input'}),
#             'item_code': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'RGT-001'}),
#             'unit_cost': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.01'}),
#             'tests': forms.CheckboxSelectMultiple(),
#         }
    
#     def __init__(self, vendor=None, *args, **kwargs):
#         super().__init__(*args, **kwargs)
#         if vendor:
#             self.fields['category'].queryset = self.fields['category'].queryset.filter(vendor=vendor)
#             self.fields['tests'].queryset = self.fields['tests'].queryset.filter(vendor=vendor)


# class StockLotForm(forms.ModelForm):
#     class Meta:
#         model = StockLot
#         fields = [
#             'item', 'lot_number', 'barcode',
#             'quantity_received', 'manufacture_date', 'expiry_date',
#             'storage_location', 'supplier', 'purchase_order',
#             'unit_cost', 'notes'
#         ]
#         widgets = {
#             'manufacture_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-input'}),
#             'expiry_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-input'}),
#             'quantity_received': forms.NumberInput(attrs={'class': 'form-input'}),
#             'unit_cost': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.01'}),
#             'notes': forms.Textarea(attrs={'rows': 3, 'class': 'form-textarea'}),
#         }
    
#     def __init__(self, vendor=None, *args, **kwargs):
#         super().__init__(*args, **kwargs)
#         if vendor:
#             self.fields['item'].queryset = InventoryItem.objects.filter(vendor=vendor)
    
#     def clean(self):
#         cleaned = super().clean()
#         expiry = cleaned.get('expiry_date')
#         manufacture = cleaned.get('manufacture_date')
        
#         if expiry and manufacture and expiry <= manufacture:
#             raise forms.ValidationError('Expiry date must be after manufacture date')
        
#         return cleaned


# class ReagentUsageForm(forms.ModelForm):
#     """Manual reagent usage entry"""
#     class Meta:
#         model = ReagentUsage
#         fields = ['stock_lot', 'quantity_used', 'usage_type', 'notes']
#         widgets = {
#             'quantity_used': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.01'}),
#             'notes': forms.Textarea(attrs={'rows': 2, 'class': 'form-textarea'}),
#         }
    
#     def __init__(self, vendor=None, *args, **kwargs):
#         super().__init__(*args, **kwargs)
#         if vendor:
#             # Only show available stock lots
#             self.fields['stock_lot'].queryset = StockLot.objects.filter(
#                 item__vendor=vendor,
#                 is_available=True,
#                 quantity_remaining__gt=0
#             ).select_related('item')


# class StockAdjustmentForm(forms.ModelForm):
#     class Meta:
#         model = StockAdjustment
#         fields = ['stock_lot', 'quantity_adjusted', 'reason', 'notes']
#         widgets = {
#             'quantity_adjusted': forms.NumberInput(attrs={
#                 'class': 'form-input',
#                 'help_text': 'Positive to add, negative to remove'
#             }),
#             'notes': forms.Textarea(attrs={'rows': 3, 'class': 'form-textarea'}),
#         }
    
#     def __init__(self, vendor=None, *args, **kwargs):
#         super().__init__(*args, **kwargs)
#         if vendor:
#             self.fields['stock_lot'].queryset = StockLot.objects.filter(
#                 item__vendor=vendor
#             ).select_related('item')


# class PurchaseOrderForm(forms.ModelForm):
#     class Meta:
#         model = PurchaseOrder
#         fields = [
#             'po_number', 'supplier', 'order_date', 
#             'expected_delivery', 'notes'
#         ]
#         widgets = {
#             'order_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-input'}),
#             'expected_delivery': forms.DateInput(attrs={'type': 'date', 'class': 'form-input'}),
#             'notes': forms.Textarea(attrs={'rows': 3, 'class': 'form-textarea'}),
#         }


# class PurchaseOrderItemForm(forms.ModelForm):
#     class Meta:
#         model = PurchaseOrderItem
#         fields = ['inventory_item', 'quantity_ordered', 'unit_price', 'notes']
#         widgets = {
#             'unit_price': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.01'}),
#             'quantity_ordered': forms.NumberInput(attrs={'class': 'form-input'}),
#         }
    
#     def __init__(self, vendor=None, *args, **kwargs):
#         super().__init__(*args, **kwargs)
#         if vendor:
#             self.fields['inventory_item'].queryset = InventoryItem.objects.filter(
#                 vendor=vendor, is_active=True
#             )






















from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import (
    InventoryCategory, InventoryItem, StockLot, ReagentUsage,
    StockAdjustment, PurchaseOrder, PurchaseOrderItem,
    StorageUnit, StorageLocation, StoredSample
)


# ==========================================
# INVENTORY ITEM FORMS
# ==========================================

class InventoryCategoryForm(forms.ModelForm):
    class Meta:
        model = InventoryCategory
        fields = ['name', 'category_type', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'category_type': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class InventoryItemForm(forms.ModelForm):
    class Meta:
        model = InventoryItem
        fields = [
            'category', 'item_code', 'name', 'manufacturer', 'catalog_number',
            'unit_of_measure', 'pack_size', 'storage_condition', 'storage_location',
            'reorder_level', 'minimum_stock', 'maximum_stock', 'unit_cost',
            'tests', 'is_active', 'requires_barcode', 'requires_lot_tracking'
        ]
        widgets = {
            'category': forms.Select(attrs={'class': 'form-select'}),
            'item_code': forms.TextInput(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'manufacturer': forms.TextInput(attrs={'class': 'form-control'}),
            'catalog_number': forms.TextInput(attrs={'class': 'form-control'}),
            'unit_of_measure': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'ml, L, tests, pcs'}),
            'pack_size': forms.NumberInput(attrs={'class': 'form-control'}),
            'storage_condition': forms.Select(attrs={'class': 'form-select'}),
            'storage_location': forms.TextInput(attrs={'class': 'form-control'}),
            'reorder_level': forms.NumberInput(attrs={'class': 'form-control'}),
            'minimum_stock': forms.NumberInput(attrs={'class': 'form-control'}),
            'maximum_stock': forms.NumberInput(attrs={'class': 'form-control'}),
            'unit_cost': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'tests': forms.SelectMultiple(attrs={'class': 'form-select', 'size': '5'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'requires_barcode': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'requires_lot_tracking': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

     
    def __init__(self, vendor=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if vendor:
            self.fields['category'].queryset = self.fields['category'].queryset.filter(vendor=vendor)
            self.fields['tests'].queryset = self.fields['tests'].queryset.filter(vendor=vendor)

    def clean(self):
        cleaned_data = super().clean()
        reorder = cleaned_data.get('reorder_level')
        minimum = cleaned_data.get('minimum_stock')
        maximum = cleaned_data.get('maximum_stock')

        if minimum and maximum and minimum > maximum:
            raise ValidationError('Minimum stock cannot be greater than maximum stock')
        
        if reorder and minimum and reorder < minimum:
            raise ValidationError('Reorder level should be at least equal to minimum stock')

        return cleaned_data


class InventoryItemSearchForm(forms.Form):
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Search by name, code, or manufacturer...'
        })
    )
    category = forms.ModelChoiceField(
        queryset=InventoryCategory.objects.all(),
        required=False,
        empty_label='All Categories',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    storage_condition = forms.ChoiceField(
        choices=[('', 'All Conditions')] + InventoryItem.STORAGE_CONDITIONS,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    status = forms.ChoiceField(
        choices=[
            ('', 'All Items'),
            ('active', 'Active Only'),
            ('inactive', 'Inactive Only'),
            ('low_stock', 'Low Stock'),
            ('out_of_stock', 'Out of Stock'),
        ],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )


# ==========================================
# STOCK LOT FORMS
# ==========================================

class StockLotForm(forms.ModelForm):
    class Meta:
        model = StockLot
        fields = [
            'item', 'lot_number', 'barcode', 'quantity_received',
            'received_date', 'manufacture_date', 'expiry_date',
            'storage_location', 'supplier', 'purchase_order',
            'unit_cost', 'notes'
        ]
        widgets = {
            'item': forms.Select(attrs={'class': 'form-select'}),
            'lot_number': forms.TextInput(attrs={'class': 'form-control'}),
            'barcode': forms.TextInput(attrs={'class': 'form-control'}),
            'quantity_received': forms.NumberInput(attrs={'class': 'form-control'}),
            'received_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'manufacture_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'expiry_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'storage_location': forms.TextInput(attrs={'class': 'form-control'}),
            'supplier': forms.TextInput(attrs={'class': 'form-control'}),
            'purchase_order': forms.TextInput(attrs={'class': 'form-control'}),
            'unit_cost': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            # If editing, set quantity_remaining to current value
            self.initial['quantity_remaining'] = self.instance.quantity_remaining
        else:
            # For new lots, quantity_remaining equals quantity_received
            if 'quantity_received' in self.data:
                self.initial['quantity_remaining'] = self.data.get('quantity_received')

    def save(self, commit=True):
        instance = super().save(commit=False)
        if not instance.pk:  # New lot
            instance.quantity_remaining = instance.quantity_received
            instance.received_by = self.initial.get('user')
        if commit:
            instance.save()
        return instance

    def clean(self):
        cleaned_data = super().clean()
        manufacture_date = cleaned_data.get('manufacture_date')
        expiry_date = cleaned_data.get('expiry_date')
        received_date = cleaned_data.get('received_date')

        if manufacture_date and expiry_date and manufacture_date >= expiry_date:
            raise ValidationError('Manufacture date must be before expiry date')
        
        if expiry_date and expiry_date <= timezone.now().date():
            raise ValidationError('Cannot add expired stock. Expiry date must be in the future.')
        
        if received_date and received_date > timezone.now().date():
            raise ValidationError('Received date cannot be in the future')

        return cleaned_data


class StockLotSearchForm(forms.Form):
    item = forms.ModelChoiceField(
        queryset=InventoryItem.objects.filter(is_active=True),
        required=False,
        empty_label='All Items',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    status = forms.ChoiceField(
        choices=[('', 'All Status')] + StockLot.LOT_STATUS,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    expiry_range = forms.ChoiceField(
        choices=[
            ('', 'All Expiry Dates'),
            ('7', 'Expiring in 7 days'),
            ('30', 'Expiring in 30 days'),
            ('90', 'Expiring in 90 days'),
            ('expired', 'Already Expired'),
        ],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )


# ==========================================
# REAGENT USAGE FORMS
# ==========================================

class ReagentUsageForm(forms.ModelForm):
    class Meta:
        model = ReagentUsage
        fields = [
            'stock_lot', 'quantity_used', 'usage_type',
            'test_assignment', 'qc_result', 'calibration', 'notes'
        ]
        widgets = {
            'stock_lot': forms.Select(attrs={'class': 'form-select'}),
            'quantity_used': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'usage_type': forms.Select(attrs={'class': 'form-select'}),
            'test_assignment': forms.Select(attrs={'class': 'form-select'}),
            'qc_result': forms.Select(attrs={'class': 'form-select'}),
            'calibration': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def clean(self):
        cleaned_data = super().clean()
        stock_lot = cleaned_data.get('stock_lot')
        quantity_used = cleaned_data.get('quantity_used')

        if stock_lot and quantity_used:
            if quantity_used > stock_lot.quantity_remaining:
                raise ValidationError(
                    f'Insufficient stock. Only {stock_lot.quantity_remaining} units available.'
                )

        return cleaned_data


# ==========================================
# STOCK ADJUSTMENT FORMS
# ==========================================

class StockAdjustmentForm(forms.ModelForm):
    class Meta:
        model = StockAdjustment
        fields = ['stock_lot', 'quantity_adjusted', 'reason', 'notes']
        widgets = {
            'stock_lot': forms.Select(attrs={'class': 'form-select'}),
            'quantity_adjusted': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Positive = Add, Negative = Remove'
            }),
            'reason': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def clean(self):
        cleaned_data = super().clean()
        stock_lot = cleaned_data.get('stock_lot')
        quantity_adjusted = cleaned_data.get('quantity_adjusted')

        if stock_lot and quantity_adjusted:
            new_quantity = stock_lot.quantity_remaining + quantity_adjusted
            if new_quantity < 0:
                raise ValidationError(
                    f'Cannot remove {abs(quantity_adjusted)} units. Only {stock_lot.quantity_remaining} units available.'
                )

        return cleaned_data


# ==========================================
# PURCHASE ORDER FORMS
# ==========================================

class PurchaseOrderForm(forms.ModelForm):
    class Meta:
        model = PurchaseOrder
        fields = [
            'po_number', 'supplier', 'status', 'order_date',
            'expected_delivery', 'tax', 'shipping', 'notes'
        ]
        widgets = {
            'po_number': forms.TextInput(attrs={'class': 'form-control'}),
            'supplier': forms.TextInput(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'order_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'expected_delivery': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'tax': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'shipping': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class PurchaseOrderItemForm(forms.ModelForm):
    class Meta:
        model = PurchaseOrderItem
        fields = ['inventory_item', 'quantity_ordered', 'unit_price', 'notes']
        widgets = {
            'inventory_item': forms.Select(attrs={'class': 'form-select'}),
            'quantity_ordered': forms.NumberInput(attrs={'class': 'form-control'}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }


# Formset for Purchase Order Items
from django.forms import inlineformset_factory

PurchaseOrderItemFormSet = inlineformset_factory(
    PurchaseOrder,
    PurchaseOrderItem,
    form=PurchaseOrderItemForm,
    extra=1,
    can_delete=True,
    min_num=1,
    validate_min=True,
)


# ==========================================
# STORAGE MANAGEMENT FORMS
# ==========================================

class StorageUnitForm(forms.ModelForm):
    class Meta:
        model = StorageUnit
        fields = [
            'name', 'unit_type', 'location', 'total_shelves',
            'total_racks', 'total_boxes', 'target_temperature',
            'current_temperature', 'is_active'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'unit_type': forms.Select(attrs={'class': 'form-select'}),
            'location': forms.TextInput(attrs={'class': 'form-control'}),
            'total_shelves': forms.NumberInput(attrs={'class': 'form-control'}),
            'total_racks': forms.NumberInput(attrs={'class': 'form-control'}),
            'total_boxes': forms.NumberInput(attrs={'class': 'form-control'}),
            'target_temperature': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
            'current_temperature': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class StorageLocationForm(forms.ModelForm):
    class Meta:
        model = StorageLocation
        fields = [
            'storage_unit', 'shelf_number', 'rack_number',
            'box_number', 'position'
        ]
        widgets = {
            'storage_unit': forms.Select(attrs={'class': 'form-select'}),
            'shelf_number': forms.NumberInput(attrs={'class': 'form-control'}),
            'rack_number': forms.NumberInput(attrs={'class': 'form-control'}),
            'box_number': forms.NumberInput(attrs={'class': 'form-control'}),
            'position': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., A1, B3'}),
        }


class StoredSampleForm(forms.ModelForm):
    class Meta:
        model = StoredSample
        fields = [
            'test_request', 'sample_id', 'sample_type',
            'storage_location', 'retention_days', 'notes'
        ]
        widgets = {
            'test_request': forms.Select(attrs={'class': 'form-select'}),
            'sample_id': forms.TextInput(attrs={'class': 'form-control'}),
            'sample_type': forms.TextInput(attrs={'class': 'form-control'}),
            'storage_location': forms.Select(attrs={'class': 'form-select'}),
            'retention_days': forms.NumberInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only show available storage locations
        self.fields['storage_location'].queryset = StorageLocation.objects.filter(
            is_occupied=False
        )


class StoredSampleRetrievalForm(forms.Form):
    retrieval_reason = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        required=True,
        label='Reason for Retrieval'
    )