# Registration: apps/accounts/forms.py (append)
from django import forms
from django.contrib.auth import get_user_model
from apps.tenants.models import Vendor
from django.contrib.auth.forms import AuthenticationForm


User = get_user_model()


class RegistrationForm(forms.ModelForm):
    password1 = forms.CharField(widget=forms.PasswordInput)
    password2 = forms.CharField(widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ('email', 'first_name', 'last_name')

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
    
# class TenantAuthenticationForm(AuthenticationForm):
#     # Use default fields (username, password) but username is email
#     username = forms.EmailField(widget=forms.EmailInput(attrs={'autofocus': True}))

# from django import forms
# from django.contrib.auth.forms import AuthenticationForm

class TenantAuthenticationForm(AuthenticationForm):
    username = forms.EmailField(
        widget=forms.EmailInput(
            attrs={
                'class': 'form-control',
                'placeholder': 'Enter your email address',
                'autofocus': True,
            }
        ),
        label='Email Address',
    )
    password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                'class': 'form-control',
                'placeholder': 'Enter your password',
            }
        ),
        label='Password',
    )
