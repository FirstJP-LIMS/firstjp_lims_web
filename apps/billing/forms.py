from decimal import Decimal
from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import (
    PriceList, TestPrice, InsuranceProvider, CorporateClient,
    BillingInformation, Payment, Invoice, InvoicePayment
)


# ==========================================
# PRICE LIST FORMS
# ==========================================

class PriceListForm(forms.ModelForm):
    """Form for creating/editing price lists"""
    
    class Meta:
        model = PriceList
        fields = [
            'name', 'price_type', 'client_name', 'contract_number',
            'discount_percentage', 'tax_percentage', 'max_discount_amount',
            'allow_overrides', 'effective_date', 'expiry_date', 'is_active'
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., AVON HMO Standard Rates'
            }),
            'price_type': forms.Select(attrs={'class': 'form-select'}),
            'client_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'HMO or Company Name'
            }),
            'contract_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Contract/Agreement Number'
            }),
            'discount_percentage': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'max': '100'
            }),
            'tax_percentage': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'max': '100'
            }),
            'max_discount_amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0'
            }),
            'allow_overrides': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'effective_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'expiry_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        effective_date = cleaned_data.get('effective_date')
        expiry_date = cleaned_data.get('expiry_date')

        if effective_date and expiry_date:
            if expiry_date <= effective_date:
                raise ValidationError('Expiry date must be after effective date.')

        return cleaned_data


class TestPriceForm(forms.ModelForm):
    """Form for setting individual test prices within a price list"""
    
    class Meta:
        model = TestPrice
        fields = ['test', 'price', 'discount_percentage', 'cost_price']
        widgets = {
            'test': forms.Select(attrs={'class': 'form-select'}),
            'price': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0'
            }),
            'discount_percentage': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'max': '100'
            }),
            'cost_price': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0'
            }),
        }

    def clean(self):
        cleaned_data = super().clean()
        price = cleaned_data.get('price')
        cost_price = cleaned_data.get('cost_price')

        if price and cost_price:
            if cost_price > price:
                raise ValidationError('Cost price cannot exceed selling price.')

        return cleaned_data


# ==========================================
# INSURANCE PROVIDER FORMS
# ==========================================

class InsuranceProviderForm(forms.ModelForm):
    """Form for managing insurance/HMO providers"""
    
    class Meta:
        model = InsuranceProvider
        fields = [
            'name', 'code', 'contact_person', 'phone', 'email', 'address',
            'payment_terms_days', 'credit_limit', 'default_copay_percentage',
            'is_active', 'requires_preauth', 'price_list'
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., AVON HMO'
            }),
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., AVON'
            }),
            'contact_person': forms.TextInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3
            }),
            'payment_terms_days': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0'
            }),
            'credit_limit': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0'
            }),
            'default_copay_percentage': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.0001',
                'min': '0',
                'max': '1',
                'placeholder': '0.10 for 10%'
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'requires_preauth': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'price_list': forms.Select(attrs={'class': 'form-select'}),
        }


# ==========================================
# CORPORATE CLIENT FORMS
# ==========================================

class CorporateClientForm(forms.ModelForm):
    """Form for managing corporate accounts"""
    
    class Meta:
        model = CorporateClient
        fields = [
            'company_name', 'bank_name', 'bank_account_number',
            'contact_person', 'phone', 'email', 'billing_address',
            'payment_terms_days', 'credit_limit', 'special_discount_percentage',
            'max_discount_amount', 'price_list', 'is_active'
        ]
        widgets = {
            'company_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Company Name'
            }),
            'bank_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Bank Name'
            }),
            'bank_account_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Account Number'
            }),
            'contact_person': forms.TextInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'billing_address': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3
            }),
            'payment_terms_days': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0'
            }),
            'credit_limit': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0'
            }),
            'special_discount_percentage': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'max': '100'
            }),
            'max_discount_amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0'
            }),
            'price_list': forms.Select(attrs={'class': 'form-select'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


# ==========================================
# BILLING INFORMATION FORMS
# ==========================================

class BillingInformationForm(forms.ModelForm):
    """Form for creating/updating billing records"""
    
    class Meta:
        model = BillingInformation
        fields = [
            'billing_type', 'price_list', 'insurance_provider',
            'policy_number', 'pre_authorization_code', 'corporate_client',
            'employee_id', 'manual_discount', 'waiver_amount', 'billing_notes'
        ]
        widgets = {
            'billing_type': forms.Select(attrs={'class': 'form-select'}),
            'price_list': forms.Select(attrs={'class': 'form-select'}),
            'insurance_provider': forms.Select(attrs={'class': 'form-select'}),
            'policy_number': forms.TextInput(attrs={'class': 'form-control'}),
            'pre_authorization_code': forms.TextInput(attrs={'class': 'form-control'}),
            'corporate_client': forms.Select(attrs={'class': 'form-select'}),
            'employee_id': forms.TextInput(attrs={'class': 'form-control'}),
            'manual_discount': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0'
            }),
            'waiver_amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0'
            }),
            'billing_notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3
            }),
        }

    def __init__(self, *args, **kwargs):
        vendor = kwargs.pop('vendor', None)
        super().__init__(*args, **kwargs)
        
        if vendor:
            self.fields['price_list'].queryset = PriceList.objects.filter(
                vendor=vendor, is_active=True
            )
            self.fields['insurance_provider'].queryset = InsuranceProvider.objects.filter(
                vendor=vendor, is_active=True
            )
            self.fields['corporate_client'].queryset = CorporateClient.objects.filter(
                vendor=vendor, is_active=True
            )

    def clean(self):
        cleaned_data = super().clean()
        billing_type = cleaned_data.get('billing_type')
        insurance_provider = cleaned_data.get('insurance_provider')
        corporate_client = cleaned_data.get('corporate_client')
        policy_number = cleaned_data.get('policy_number')

        # Validation based on billing type
        if billing_type == 'HMO':
            if not insurance_provider:
                raise ValidationError('Insurance provider is required for HMO billing.')
            if not policy_number:
                raise ValidationError('Policy number is required for HMO billing.')
        
        elif billing_type == 'CORPORATE':
            if not corporate_client:
                raise ValidationError('Corporate client is required for corporate billing.')

        return cleaned_data


# ==========================================
# PAYMENT FORMS
# ==========================================

class PaymentForm(forms.ModelForm):
    """Form for recording payments"""
    
    class Meta:
        model = Payment
        fields = [
            'amount', 'payment_method', 'transaction_reference',
            'payment_date', 'notes'
        ]
        widgets = {
            'amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0.01'
            }),
            'payment_method': forms.Select(attrs={'class': 'form-select'}),
            'transaction_reference': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'POS/Transfer Reference'
            }),
            'payment_date': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2
            }),
        }

    def __init__(self, *args, **kwargs):
        self.billing = kwargs.pop('billing', None)
        super().__init__(*args, **kwargs)
        
        if self.billing:
            balance = self.billing.get_balance_due()
            self.fields['amount'].widget.attrs['max'] = str(balance)
            self.fields['amount'].help_text = f'Balance due: ₦{balance:,.2f}'

    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        if amount and amount <= Decimal('0'):
            raise ValidationError('Payment amount must be greater than zero.')
        
        if self.billing:
            balance = self.billing.get_balance_due()
            if amount > balance:
                raise ValidationError(f'Payment amount (₦{amount:,.2f}) exceeds balance due (₦{balance:,.2f}).')
        
        return amount


# ==========================================
# INVOICE FORMS
# ==========================================

class InvoiceForm(forms.ModelForm):
    """Form for creating invoices"""
    
    class Meta:
        model = Invoice
        fields = [
            'invoice_date', 'due_date', 'insurance_provider',
            'corporate_client', 'period_start', 'period_end', 'notes'
        ]
        widgets = {
            'invoice_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'due_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'insurance_provider': forms.Select(attrs={'class': 'form-select'}),
            'corporate_client': forms.Select(attrs={'class': 'form-select'}),
            'period_start': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'period_end': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3
            }),
        }

    def __init__(self, *args, **kwargs):
        vendor = kwargs.pop('vendor', None)
        super().__init__(*args, **kwargs)
        
        if vendor:
            self.fields['insurance_provider'].queryset = InsuranceProvider.objects.filter(
                vendor=vendor, is_active=True
            )
            self.fields['corporate_client'].queryset = CorporateClient.objects.filter(
                vendor=vendor, is_active=True
            )

    def clean(self):
        cleaned_data = super().clean()
        insurance_provider = cleaned_data.get('insurance_provider')
        corporate_client = cleaned_data.get('corporate_client')
        period_start = cleaned_data.get('period_start')
        period_end = cleaned_data.get('period_end')
        invoice_date = cleaned_data.get('invoice_date')
        due_date = cleaned_data.get('due_date')

        # Must have either insurance or corporate client
        if not insurance_provider and not corporate_client:
            raise ValidationError('Please select either an insurance provider or corporate client.')
        
        if insurance_provider and corporate_client:
            raise ValidationError('Please select only one: insurance provider OR corporate client.')

        # Period validation
        if period_start and period_end:
            if period_end <= period_start:
                raise ValidationError('Period end date must be after period start date.')

        # Due date validation
        if invoice_date and due_date:
            if due_date < invoice_date:
                raise ValidationError('Due date cannot be before invoice date.')

        return cleaned_data


class InvoicePaymentForm(forms.ModelForm):
    """Form for recording invoice payments"""
    
    class Meta:
        model = InvoicePayment
        fields = [
            'amount', 'payment_date', 'payment_method',
            'reference_number', 'notes'
        ]
        widgets = {
            'amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0.01'
            }),
            'payment_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'payment_method': forms.Select(attrs={'class': 'form-select'}),
            'reference_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Payment Reference'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2
            }),
        }

    def __init__(self, *args, **kwargs):
        self.invoice = kwargs.pop('invoice', None)
        super().__init__(*args, **kwargs)
        
        if self.invoice:
            balance = self.invoice.balance_due()
            self.fields['amount'].widget.attrs['max'] = str(balance)
            self.fields['amount'].help_text = f'Balance due: ₦{balance:,.2f}'

    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        if amount and amount <= Decimal('0'):
            raise ValidationError('Payment amount must be greater than zero.')
        
        if self.invoice:
            balance = self.invoice.balance_due()
            if amount > balance:
                raise ValidationError(f'Payment exceeds balance due (₦{balance:,.2f}).')
        
        return amount


# ==========================================
# FILTER FORMS
# ==========================================

class BillingFilterForm(forms.Form):
    """Form for filtering billing records"""
    
    billing_type = forms.ChoiceField(
        choices=[('', 'All Types')] + BillingInformation.BILLING_TYPES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    payment_status = forms.ChoiceField(
        choices=[('', 'All Status')] + BillingInformation.PAYMENT_STATUS,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )


class InvoiceFilterForm(forms.Form):
    """Form for filtering invoices"""
    
    status = forms.ChoiceField(
        choices=[('', 'All Status')] + Invoice.INVOICE_STATUS,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    client_type = forms.ChoiceField(
        choices=[
            ('', 'All Clients'),
            ('HMO', 'Insurance Providers'),
            ('CORPORATE', 'Corporate Clients')
        ],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )




