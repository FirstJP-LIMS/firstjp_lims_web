# apps/accounts/forms.py
from django import forms
from django.contrib.auth import get_user_model
from apps.tenants.models import Vendor
from django.contrib.auth.forms import AuthenticationForm

User = get_user_model()

class RegistrationForm(forms.ModelForm):
    password1 = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Create a strong password'
        }),
        label="Password"
    )
    password2 = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Confirm your password'
        }),
        label="Confirm Password"
    )

    class Meta:
        model = User
        fields = ('email', 'first_name', 'last_name')
        widgets = {
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'your@email.com'
            }),
            'first_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'First Name'
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Last Name'
            }),
        }

    def clean_password2(self):
        p1 = self.cleaned_data.get('password1')
        p2 = self.cleaned_data.get('password2')
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError('Passwords do not match')
        return p2

    def save(self, commit=True, vendor=None, role='lab_staff'):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        if vendor:
            user.vendor = vendor
        user.role = role
        if commit:
            user.save()
        return user


class TenantAuthenticationForm(AuthenticationForm):
    username = forms.EmailField(
        widget=forms.EmailInput(
            attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent',
                'placeholder': 'Enter your email address',
                'autofocus': True,
            }
        ),
        label='Email Address',
    )
    password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent',
                'placeholder': 'Enter your password',
            }
        ),
        label='Password',
    )




from django import forms
from .models import VendorProfile

class VendorProfileForm(forms.ModelForm):
    class Meta:
        model = VendorProfile
        fields = [
            "logo",
            "registration_number",
            "contact_number",
            "office_address",
            "office_city_state",
            "office_country",
            "office_zipcode",
        ]

        widgets = {
            "office_address": forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
            "office_city_state": forms.TextInput(attrs={"class": "form-control"}),
            "office_country": forms.TextInput(attrs={"class": "form-control"}),
            "office_zipcode": forms.TextInput(attrs={"class": "form-control"}),
            "contact_number": forms.TextInput(attrs={"class": "form-control"}),
            "registration_number": forms.TextInput(attrs={"class": "form-control"}),
        }
