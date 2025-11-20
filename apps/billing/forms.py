from django import forms
from .models import (
    PriceList, TestPrice, InsuranceProvider, 
    CorporateClient, Invoice, Payment, InvoicePayment
)


class PriceListForm(forms.ModelForm):
    class Meta:
        model = PriceList
        fields = [
            'name', 'price_type', 'client_name', 'contract_number',
            'discount_percentage', 'effective_date', 'expiry_date', 'is_active'
        ]
        widgets = {
            'effective_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-input'}),
            'expiry_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-input'}),
            'discount_percentage': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.01'}),
        }


class TestPriceForm(forms.ModelForm):
    class Meta:
        model = TestPrice
        fields = ['price_list', 'test', 'price', 'cost_price']
        widgets = {
            'price': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.01'}),
            'cost_price': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.01'}),
        }
    
    def __init__(self, vendor=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if vendor:
            self.fields['price_list'].queryset = PriceList.objects.filter(vendor=vendor)
            self.fields['test'].queryset = self.fields['test'].queryset.filter(vendor=vendor)


class InsuranceProviderForm(forms.ModelForm):
    class Meta:
        model = InsuranceProvider
        fields = [
            'name', 'code', 'contact_person', 'phone', 'email', 'address',
            'payment_terms_days', 'credit_limit', 'requires_preauth',
            'price_list', 'is_active'
        ]
        widgets = {
            'address': forms.Textarea(attrs={'rows': 3, 'class': 'form-textarea'}),
            'credit_limit': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.01'}),
        }
    
    def __init__(self, vendor=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if vendor:
            self.fields['price_list'].queryset = PriceList.objects.filter(vendor=vendor)


class CorporateClientForm(forms.ModelForm):
    class Meta:
        model = CorporateClient
        fields = [
            'company_name', 'account_number', 'contact_person',
            'phone', 'email', 'billing_address',
            'payment_terms_days', 'credit_limit', 'price_list', 'is_active'
        ]
        widgets = {
            'billing_address': forms.Textarea(attrs={'rows': 3, 'class': 'form-textarea'}),
            'credit_limit': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.01'}),
        }
    
    def __init__(self, vendor=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if vendor:
            self.fields['price_list'].queryset = PriceList.objects.filter(vendor=vendor)


class PaymentForm(forms.ModelForm):
    """For cash payments from patients"""
    class Meta:
        model = Payment
        fields = ['amount', 'payment_method', 'transaction_reference', 'notes']
        widgets = {
            'amount': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.01'}),
            'transaction_reference': forms.TextInput(attrs={'class': 'form-input'}),
            'notes': forms.Textarea(attrs={'rows': 2, 'class': 'form-textarea'}),
        }


class InvoiceForm(forms.ModelForm):
    class Meta:
        model = Invoice
        fields = [
            'invoice_number', 'invoice_date', 'due_date',
            'insurance_provider', 'corporate_client',
            'period_start', 'period_end', 'notes'
        ]
        widgets = {
            'invoice_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-input'}),
            'due_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-input'}),
            'period_start': forms.DateInput(attrs={'type': 'date', 'class': 'form-input'}),
            'period_end': forms.DateInput(attrs={'type': 'date', 'class': 'form-input'}),
            'notes': forms.Textarea(attrs={'rows': 3, 'class': 'form-textarea'}),
        }
    
    def clean(self):
        cleaned = super().clean()
        insurance = cleaned.get('insurance_provider')
        corporate = cleaned.get('corporate_client')
        
        # Must have either insurance or corporate, but not both
        if not insurance and not corporate:
            raise forms.ValidationError('Must select either Insurance Provider or Corporate Client')
        if insurance and corporate:
            raise forms.ValidationError('Cannot select both Insurance Provider and Corporate Client')
        
        return cleaned


class InvoicePaymentForm(forms.ModelForm):
    """For payments received from HMO/Corporate"""
    class Meta:
        model = InvoicePayment
        fields = ['amount', 'payment_date', 'payment_method', 'reference_number', 'notes']
        widgets = {
            'amount': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.01'}),
            'payment_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-input'}),
            'notes': forms.Textarea(attrs={'rows': 2, 'class': 'form-textarea'}),
        }