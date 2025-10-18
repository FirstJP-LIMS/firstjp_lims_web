# Django Multi-tenant Auth & Middleware Scaffold
# This document contains multiple files (path headers + code) to copy into your project.
# Files included:
# - apps/accounts/models.py
# - apps/accounts/forms.py
# - apps/accounts/views.py
# - apps/core/managers.py
# - apps/core/middleware.py
# - templates/registration/login.html
# - universalis_project/settings/base.py (snippets to add)

# =========================
# File: apps/accounts/models.py
# =========================
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.utils import timezone
from django.conf import settings
from tenants.models import Vendor


class CustomUserManager(BaseUserManager):
    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError('The given email must be set')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')
        return self._create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    ROLE_CHOICES = [
        ('platform_admin', 'Platform Admin'),
        ('vendor_admin', 'Vendor Admin'),
        ('lab_staff', 'Lab Staff'),
    ]

    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)

    # Link user to a vendor (nullable for platform admins)
    vendor = models.ForeignKey(Vendor, null=True, blank=True, on_delete=models.SET_NULL)
    role = models.CharField(max_length=32, choices=ROLE_CHOICES, default='lab_staff')

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = CustomUserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    def __str__(self):
        return self.email

    @property
    def is_platform_admin(self):
        return self.is_superuser or self.role == 'platform_admin'

# =========================
# File: apps/accounts/forms.py
# =========================
from django import forms
from django.contrib.auth.forms import AuthenticationForm


class TenantAuthenticationForm(AuthenticationForm):
    # Use default fields (username, password) but username is email
    username = forms.EmailField(widget=forms.EmailInput(attrs={'autofocus': True}))

# =========================
# File: apps/accounts/views.py
# =========================
from django.contrib.auth import login as auth_login
from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import TemplateView


class TenantLoginView(LoginView):
    template_name = 'registration/login.html'
    authentication_form = None  # set in urls or dynamically

    def get_form_class(self):
        from .forms import TenantAuthenticationForm
        return TenantAuthenticationForm

    def form_valid(self, form):
        # After login, ensure user belongs to the current tenant (unless platform admin)
        user = form.get_user()
        request = self.request
        tenant = getattr(request, 'tenant', None)
        if user.is_platform_admin:
            auth_login(request, user)
            return redirect(self.get_success_url())

        # If user is not platform admin, ensure vendor matches request.tenant
        if tenant is None:
            # No tenant resolved: deny access or redirect to central landing
            return redirect(reverse_lazy('no_tenant'))

        if user.vendor_id and user.vendor_id == tenant.internal_id:
            auth_login(request, user)
            return redirect(self.get_success_url())

        # Mismatch: deny
        return redirect(reverse_lazy('login'))


class TenantLogoutView(LogoutView):
    next_page = reverse_lazy('login')


class DashboardView(TemplateView):
    template_name = 'admin_ui/dashboard.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['tenant'] = getattr(self.request, 'tenant', None)
        return ctx

# =========================
# File: apps/core/managers.py
# =========================
from django.db import models


class TenantAwareManager(models.Manager):
    def for_tenant(self, tenant):
        if tenant is None:
            return self.get_queryset().none()
        # tenant may be Vendor instance or UUID
        tenant_obj = tenant if hasattr(tenant, 'internal_id') else None
        if tenant_obj:
            return self.get_queryset().filter(tenant=tenant_obj)
        # fallback
        return self.get_queryset().filter(tenant__internal_id=tenant)

# =========================
# File: apps/core/middleware.py
# =========================
from django.utils.deprecation import MiddlewareMixin
from tenants.models import VendorDomain
from django.http import HttpResponseNotFound


class TenantMiddleware(MiddlewareMixin):
    """Resolve tenant from Host header or X-Tenant-ID header and attach to request."""

    def process_request(self, request):
        host = request.get_host().split(':')[0].lower()

        # Allow explicit header override (useful for API clients / tests)
        tenant_header = request.headers.get('X-Tenant-ID') or request.META.get('HTTP_X_TENANT_ID')

        tenant = None
        if tenant_header:
            # tenant_header expected to be tenant_id (human readable) or UUID
            domain_qs = VendorDomain.objects.select_related('vendor').filter(vendor__tenant_id=tenant_header)
            domain = domain_qs.first()
            if domain:
                tenant = domain.vendor
        else:
            try:
                domain = VendorDomain.objects.select_related('vendor').get(domain_name=host)
                tenant = domain.vendor
            except VendorDomain.DoesNotExist:
                tenant = None

        request.tenant = tenant

        # If you want to block unknown domains, return a response here
        # if not tenant:
        #     return HttpResponseNotFound('Tenant not found')

# =========================
# File: templates/registration/login.html
# (Place this under project templates path: templates/registration/login.html)
# =========================
"""
{% extends "base.html" %}

{% block content %}
  <div class="login-box">
    <h2>Sign in{% if tenant %} - {{ tenant.name }}{% endif %}</h2>
    <form method="post" novalidate>
      {% csrf_token %}
      {{ form.non_field_errors }}
      <div>
        <label for="id_username">Email</label>
        {{ form.username }}
      </div>
      <div>
        <label for="id_password">Password</label>
        {{ form.password }}
      </div>
      <button type="submit">Sign in</button>
    </form>
  </div>
{% endblock %}
"""

# =========================
# Snippet: universalis_project/settings/base.py
# Add / modify these settings as needed. Place this snippet into your base.py settings.
# =========================
"""
# Add 'apps.accounts', 'apps.tenants', 'apps.core', etc. to INSTALLED_APPS
INSTALLED_APPS += [
    'apps.accounts',
    'apps.tenants',
    'apps.core',
    'apps.integrations',
    'apps.labs',
    'apps.admin_ui',
]

# Custom user model
AUTH_USER_MODEL = 'accounts.User'

# Middleware: ensure TenantMiddleware is early in the chain (after security middleware)
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    # ... other middleware ...
    'apps.core.middleware.TenantMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    # ... the rest ...
]

# Templates: ensure 'templates' path is included
TEMPLATES[0]['DIRS'] = [BASE_DIR / 'templates']

LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = '/'
"""

# End of scaffold

# =========================
# Registration: apps/accounts/forms.py (append)
# =========================
from django import forms
from django.contrib.auth import get_user_model
from tenants.models import Vendor

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

# =========================
# Registration view: apps/accounts/views.py (append)
# =========================
from django.views.generic.edit import FormView
from django.urls import reverse_lazy
from django.shortcuts import get_object_or_404
from .forms import RegistrationForm
from tenants.models import Vendor


class TenantRegistrationView(FormView):
    template_name = 'registration/register.html'
    form_class = RegistrationForm
    success_url = reverse_lazy('login')

    def dispatch(self, request, *args, **kwargs):
        # Only allow registration when tenant resolved or allow a public signup policy
        self.tenant = getattr(request, 'tenant', None)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        # If tenant exists, assign user to tenant. Otherwise, registration is blocked.
        if not self.tenant:
            form.add_error(None, 'Tenant could not be resolved. Contact support.')
            return self.form_invalid(form)

        # Default role: lab_staff. Vendor_admin creation should be restricted to platform_admin or invite flow.
        form.save(vendor=self.tenant, role='lab_staff')
        return super().form_valid(form)


# Admin-only vendor-admin creation (example function)
from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import render, redirect


def is_platform_admin(user):
    return user.is_authenticated and user.is_platform_admin

@user_passes_test(is_platform_admin)
def create_vendor_admin(request, vendor_id):
    vendor = get_object_or_404(Vendor, internal_id=vendor_id)
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            form.save(vendor=vendor, role='vendor_admin')
            return redirect('admin:tenants_vendor_change', vendor.internal_id)
    else:
        form = RegistrationForm()
    return render(request, 'registration/create_vendor_admin.html', {'form': form, 'vendor': vendor})

# =========================
# Templates: templates/registration/register.html
# =========================
"""
{% extends 'base.html' %}

{% block content %}
  <div class="register-box">
    <h2>Register for {{ tenant.name }}</h2>
    <form method="post">
      {% csrf_token %}
      {{ form.non_field_errors }}
      <div>
        <label for="id_email">Email</label>
        {{ form.email }}
      </div>
      <div>
        <label for="id_first_name">First name</label>
        {{ form.first_name }}
      </div>
      <div>
        <label for="id_last_name">Last name</label>
        {{ form.last_name }}
      </div>
      <div>
        <label for="id_password1">Password</label>
        {{ form.password1 }}
      </div>
      <div>
        <label for="id_password2">Confirm password</label>
        {{ form.password2 }}
      </div>
      <button type="submit">Register</button>
    </form>
  </div>
{% endblock %}
"""

# =========================
# URLs snippet: universalis_project/urls.py (append)
# =========================
"""
from django.urls import path, include
from apps.accounts.views import TenantLoginView, TenantLogoutView, TenantRegistrationView

urlpatterns = [
    path('accounts/login/', TenantLoginView.as_view(), name='login'),
    path('accounts/logout/', TenantLogoutView.as_view(), name='logout'),
    path('accounts/register/', TenantRegistrationView.as_view(), name='register'),
    # ... other urls ...
]
"""

# =========================
# Notes and Security
# =========================
# - For Vendor Admin creation, use invite tokens (email-based) rather than open registration.
# - Consider restricting /accounts/register/ to only allow lab_staff creation; vendor_admin must be created by platform admin or via an invite.
# - Add email verification if you will use sensitive operations.
# - The registration flow above requires tenant to be resolved by middleware; for API-based onboarding, provide an invite and a one-time token.
