from django.core.cache import cache

cache.set("greeting", "Hello from Redis!", timeout=60)
print(cache.get("greeting"))  # should print "Hello from Redis!"



if ENVIRONMENT == "production":
    # Production with Redis
    REDIS_URL = os.getenv('REDIS_URL')  # From Render or external provider
    
    if REDIS_URL:
        # Using REDIS_URL (preferred for Render)
        CACHES = {
            "default": {
                "BACKEND": "django_redis.cache.RedisCache",
                "LOCATION": REDIS_URL,
                "OPTIONS": {
                    "CLIENT_CLASS": "django_redis.client.DefaultClient",
                    "SOCKET_CONNECT_TIMEOUT": 5,  # Timeout if Redis is down
                    "SOCKET_TIMEOUT": 5,
                    "RETRY_ON_TIMEOUT": True,
                    "MAX_CONNECTIONS": 50,  # Connection pool size
                    "CONNECTION_POOL_KWARGS": {
                        "max_connections": 50,
                        "retry_on_timeout": True,
                    },
                    # Optional: Add compression for large objects
                    # "COMPRESSOR": "django_redis.compressors.zlib.ZlibCompressor",
                },
                "KEY_PREFIX": "lims",  # Prefix all keys with 'lims:'
                "TIMEOUT": 900,  # Default timeout: 15 minutes
            }
        }
    else:
        # Fallback to local memory if Redis not configured
        CACHES = {
            "default": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                "LOCATION": "lims-fallback-cache",
            }
        }
else:
    # Development - use local memory cache
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "lims-dev-cache",
            "OPTIONS": {
                "MAX_ENTRIES": 2000,
            }
        }
    }


"""
Alright... I will be sharing my code, all necessary files, and note the email is not unique, I have written it in such a way that one email can be reused to registered with different vendors... --- # apps/core/middleware.py  
from django.utils.deprecation import MiddlewareMixin
from django.http import HttpResponseRedirect, HttpResponseNotFound
from django.conf import settings
from django.urls import reverse
from apps.tenants.models import VendorDomain, Vendor
import logging

logger = logging.getLogger(__name__)


class TenantMiddleware(MiddlewareMixin):
    """
    Tenant Middleware (NO CACHING)
    - Supports API header "X-Tenant-ID"
    - Supports browser subdomains (VendorDomain)
    - Performs direct DB lookup only
    """

    def process_request(self, request):
        host = request.get_host().split(':')[0].lower()
        tenant_header = request.headers.get('X-Tenant-ID') or request.META.get('HTTP_X_TENANT_ID')
        tenant = None

        # 1️⃣ Header-based tenant lookup (API clients)
        if tenant_header:
            tenant = self._get_tenant_by_header(tenant_header)

        # 2️⃣ Domain-based tenant lookup (browser access)
        if not tenant:
            tenant = self._get_tenant_by_domain(host)

        # 3️⃣ Attach tenant or set platform mode
        request.tenant = tenant
        request.is_platform = tenant is None

        # 4️⃣ Reject unknown vendor subdomains
        if not tenant and host not in getattr(settings, "GLOBAL_HOSTS", []):
            return HttpResponseNotFound(
                "<h1>Vendor Not Found</h1>"
                "<p>This laboratory subdomain is not registered or has been deactivated.</p>"
                f"<p><a href='https://{settings.PLATFORM_BASE_DOMAIN}'>Return to main platform</a></p>"
            )

        # 5️⃣ Redirect vendor root to vendor login
        if tenant and request.path == "/":
            return HttpResponseRedirect(reverse('account:login'))
            # return HttpResponseRedirect(reverse('account:auth_landing'))

        return None

    # ----------------------------------------------------------------------
    # INTERNAL METHODS (NO CACHE)
    # ----------------------------------------------------------------------

    def _get_tenant_by_header(self, tenant_id):
        """Resolve tenants via X-Tenant-ID header (direct DB lookup)."""
        try:
            return Vendor.objects.get(
                tenant_id=tenant_id,
                is_active=True
            )
        except Vendor.DoesNotExist:
            return None

    def _get_tenant_by_domain(self, host):
        """Resolve tenants via VendorDomain (direct DB lookup)."""
        try:
            domain = VendorDomain.objects.select_related('vendor').get(
                domain_name=host
            )
            return domain.vendor if domain.vendor.is_active else None
        except VendorDomain.DoesNotExist:
            return None
 . # apps/core/managers.py
from django.db import models

class TenantAwareManager(models.Manager):
    """
    Custom manager that always requires a tenant object to scope the queryset.
    """
    def for_tenant(self, tenant):
        """Returns a queryset filtered by the provided Vendor/Tenant object."""
        if not tenant:
            # Prevent accidental querying without a tenant (good security measure)
            raise ValueError("Tenant object must be provided for a tenant-aware query.")
        return self.get_queryset().filter(tenant=tenant)
        
    def get_queryset(self):
        # Override to potentially add global filters, but for tenant models,
        # To resolve un-scoped for .for_tenant()
        return super().get_queryset().......  # apps/tenants/models.py 
"""
Tenants management: Models to be used for lab owners who wants to share our platform to analyze their samples.. 
Unique domain name attached to individual tenants.
"""
import uuid
from django.db import models
from django.db import transaction
# from django.db.models import Max

PLAN_CHOICES = [
    ("1", "BASIC"), # 1 - 20 users
    ("2", "STANDARD"), # 21 - 50 users
    ("2", "PREMIUM"), # 51 - 100 users
    ("3", "PLATINUM"), # 100+ users
]

# Set up profile     
class Vendor(models.Model):
    internal_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, unique=True)
    tenant_id = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=255)
    contact_email = models.EmailField(unique=True)
    subdomain_prefix = models.SlugField(
        max_length=64,
        unique=True,
        blank=True,
        null=True,
        help_text="Subdomain prefix for this vendor (e.g., carbonilab)."
    )
    # ACCESS & SUBSCRIPTION
    is_active = models.BooleanField(default=False, help_text="Set to False if subscription lapses or vendor is disabled.")
    
    plan_type = models.CharField(max_length=50,
        choices=PLAN_CHOICES,
        default='BASIC',
        help_text="Plan type for this vendor.",
    )

    # FLEXIBLE METADATA
    # configuration = models.JSONField(default=dict, blank=True, help_text="LIS-specific settings (logo, timezone, features).")
    billing_metadata = models.JSONField( default=dict, blank=True, help_text="External IDs: Stripe Customer ID, Subscription ID, etc.")

    created_at = models.DateTimeField(auto_now_add=True)

    # generate vendor id  
    def save(self, *args, **kwargs):
        if not self.tenant_id:
            with transaction.atomic():
                last_vendor = Vendor.objects.select_for_update().order_by('-created_at').first()
                if last_vendor and last_vendor.tenant_id.startswith('LAB'):
                    try:
                        current_number = int(last_vendor.tenant_id.replace('LAB', ''))
                    except ValueError:
                        current_number = 0
                else:
                    current_number = 0
                next_number = current_number + 1
                self.tenant_id = f"LAB{next_number:04d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.tenant_id})"


class VendorDomain(models.Model):
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='domains')
    domain_name = models.CharField(
        max_length=255,
        unique=True,
        db_index=True,
        help_text="The full domain/subdomain used by this vendor."
    )
    is_primary = models.BooleanField(default=True)

    class Meta:
        # Only one domain can be marked as primary to a vendor
        unique_together = ('vendor', 'is_primary')

    def __str__(self):
        return self.domain_name

........ # apps/tenants/signals.py 
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
import logging
from .models import Vendor, VendorDomain

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Vendor)
def handle_vendor_domain(sender, instance, created, **kwargs):
    """
    Ensure VendorDomain exists for each Vendor:
    - Constructs domain: subdomain_prefix + PLATFORM_BASE_DOMAIN
    - Ensures only one primary domain per vendor
    - Updates domain_name if subdomain changes
    """

    if not instance.subdomain_prefix:
        # Fall back to tenant_id if no subdomain
        subdomain = instance.tenant_id.lower()
    else:
        subdomain = instance.subdomain_prefix.lower()

    base_domain = getattr(settings, 'PLATFORM_BASE_DOMAIN', 'localhost.test')
    full_domain = f"{subdomain}.{base_domain}"

    try:
        # Check if a primary domain exists
        domain_obj = VendorDomain.objects.filter(vendor=instance, is_primary=True).first()

        if domain_obj:
            # Update domain name if changed
            if domain_obj.domain_name != full_domain:
                domain_obj.domain_name = full_domain
                domain_obj.save(update_fields=['domain_name'])
                logger.info(f"Updated VendorDomain for {instance.tenant_id}: {full_domain}")
        else:
            # No primary domain exists → create one
            VendorDomain.objects.create(
                vendor=instance,
                domain_name=full_domain,
                is_primary=True
            )
            logger.info(f"Created VendorDomain for {instance.tenant_id}: {full_domain}")

    except Exception as e:
        logger.error(f"Error creating/updating VendorDomain for {instance.tenant_id}: {e}")

    # Optional: print for dev purposes
    print(f"✅ Vendor domain set: {full_domain}")

# apps/account/models.py
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone
from apps.tenants.models import Vendor
from phonenumber_field.modelfields import PhoneNumberField
# from geopy.geocoders import Nominatim
import uuid
from django.db import transaction


class CustomUserManager(BaseUserManager):
    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError('Email must be set')
        
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
        """ 
        Create platform-level superuser (vendor=None for global access).
        """
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('vendor', None)  # ✅ Platform admins have no vendor
        
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True')
        
        return self._create_user(email, password, **extra_fields)
    
    def get_by_natural_key(self, username):
        """
        Override to prevent uniqueness assumption.
        This is called by Django's authentication system.
        """
        # We can't lookup by email alone since it's not unique
        # This method won't be used with our custom backend
        raise NotImplementedError(
            "Use VendorEmailBackend for authentication, not get_by_natural_key"
        )
    


# User setup   
class User(AbstractBaseUser, PermissionsMixin):
    ROLE_CHOICES = [
        ('platform_admin', 'Platform Admin'),
        ('vendor_admin', 'Vendor Admin'),
        ('lab_staff', 'Lab Staff'),
        ('clinician', 'Clinician'),
        ('patient', 'Patient'),
        ('learner', 'Learner'), # Student
        ('facilitator', 'Facilitator'),
    ]

    email = models.EmailField()
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    contact_number = PhoneNumberField(blank=True, null=True)
    vendor = models.ForeignKey(Vendor, null=True, blank=True, on_delete=models.SET_NULL)
    role = models.CharField(max_length=32, choices=ROLE_CHOICES, default='lab_staff')
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = CustomUserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    class Meta:
        unique_together = [['email', 'vendor']] 

    # Suppress the warning since we have custom authentication
    @classmethod
    def check(cls, **kwargs):
        errors = super().check(**kwargs)
        # Filter out the W004 warning about non-unique USERNAME_FIELD
        errors = [e for e in errors if e.id != 'auth.W004']
        return errors
    
    @property
    def is_platform_admin(self):
        return self.is_superuser or self.role == 'platform_admin'

    def __str__(self):
        return f"{self.first_name} ({self.email}) is a/an {self.role}"


class BaseProfile(models.Model):
    logo = models.ImageField(upload_to='logos/', blank=True, null=True, help_text="Company Logo!")
    office_address = models.TextField(blank=True, help_text="e.g. - 42, Awolowo Road, Old-Bodija")
    office_city_state = models.CharField(max_length=100, blank=True, help_text="Victoria-Island, Lagos")
    office_country = models.CharField(max_length=100, blank=True, help_text="Nigeria")
    office_zipcode = models.CharField(max_length=20, blank=True, help_text="200200")
    latitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True, help_text="23.56")
    longitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True, help_text="23.56")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    @property
    def is_complete(self):
        return all([
            self.entity_img,
            self.office_address,
            self.office_city_state,
            self.office_country,
            self.office_zipcode,
        ])


class VendorProfile(BaseProfile):
    vendor = models.OneToOneField(Vendor, on_delete=models.CASCADE, related_name='profile')
    registration_number = models.CharField(max_length=100, blank=True, null=True)
    contact_number = PhoneNumberField(blank=True, null=True)

    def __str__(self):
        return f"Profile of {self.vendor.name}"

    def save(self, *args, **kwargs):
        if self.office_address and self.office_city_state and self.office_country:
            full_address = f"{self.office_address}, {self.office_city_state}, {self.office_country}, {self.office_zipcode}"
            # try:
            #     geolocator = Nominatim(user_agent="firstjp_lims")
            #     location = geolocator.geocode(full_address)
            #     if location:
            #         self.latitude = location.latitude
            #         self.longitude = location.longitude
            # except Exception:
            #     # Silently fail if geocoding doesn't work
            #     pass
        super().save(*args, **kwargs)

# apps/account/context_processors.py
from .models import VendorProfile

def vendor_context(request):
    vendor = getattr(request, "tenant", None)
    vendor_profile = None

    if vendor:
        try:
            vendor_profile = VendorProfile.objects.get(vendor=vendor)
        except VendorProfile.DoesNotExist:
            vendor_profile = None

    return {
        "vendor": vendor,
        "vendor_profile": vendor_profile,
    }      ................... # apps/accounts/backends.py
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model

User = get_user_model()

class VendorEmailBackend(ModelBackend):
    """
    Authenticate using email + tenant (vendor).
    
    Handles two authentication scenarios:
    1. Tenant-scoped users: Must match email AND vendor
    2. Platform admins: email with vendor=None (global access)
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None or password is None:
            return None

        # Get tenant from request (set by middleware)
        tenant = getattr(request, 'tenant', None)
        
        try:
            if tenant:
                # Tenant-scoped authentication
                # Find user with matching email AND vendor
                user = User.objects.get(
                    email__iexact=username,
                    vendor=tenant,
                    is_active=True  # ✅ Only active users
                )
            else:
                # Platform-level authentication (no tenant subdomain)
                # Only allow platform admins (vendor=None) to login on main domain
                user = User.objects.get(
                    email__iexact=username,
                    vendor__isnull=True,
                    is_active=True
                )
        except User.DoesNotExist:
            # User not found for this tenant/email combination
            return None
        except User.MultipleObjectsReturned:
            # This should never happen with unique_together constraint
            # But handle it gracefully just in case
            return None

        # Verify password
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        
        return None

    def get_user(self, user_id):
        """
        Retrieve user by ID (used by Django session authentication).
        """
        try:
            user = User.objects.get(pk=user_id)
            return user if self.user_can_authenticate(user) else None
        except User.DoesNotExist:
            return None

........... 
# app/accounts/views.py
from django.shortcuts import render, redirect, get_object_or_404, Http404
from django.views.generic import TemplateView
from apps.tenants.models import Vendor
from .forms import RegistrationForm, TenantAuthenticationForm, VendorProfile, VendorProfileForm, TenantPasswordResetForm
from django.urls import reverse, reverse_lazy
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import user_passes_test, login_required
from django.shortcuts import render, redirect
from django_ratelimit.decorators import ratelimit


ALLOWED_PUBLIC_ROLES = ['lab_staff', 'clinician', 'patient']

def tenant_register_by_role(request, role_name):
    """
    Handles registration for lab_staff, clinician, or patient, scoped to the current tenant.
    """
    tenant = getattr(request, 'tenant', None)
    
    # Input validation
    if role_name not in ALLOWED_PUBLIC_ROLES:
        raise Http404("Invalid registration path or user role.")
    
    if not tenant:
        messages.error(request, "Cannot register. Tenant could not be resolved. Contact support.")
        return redirect('account:login')  # ✅ Better redirect
    
    role_display_name = role_name.replace('_', ' ').title()

    if request.method == 'POST':
        form = RegistrationForm(request.POST, vendor=tenant)  # ✅ Pass vendor to form
        
        if form.is_valid():
            # Save with transaction for safety
            try:
                user = form.save(vendor=tenant, role=role_name)
                messages.success(
                    request, 
                    f"{role_display_name} account created successfully for {tenant.name}. You can now log in."
                )
                return redirect(reverse('account:login'))  # ✅ Use namespaced URL
            except Exception as e:
                messages.error(request, f"Registration failed: {str(e)}")
    else:
        form = RegistrationForm(vendor=tenant)  # ✅ Pass vendor

    context = {
        'form': form,
        'tenant': tenant,
        'lab_name': tenant.name,
        'role_name': role_display_name,
        'role_key': role_name,
    }
    return render(request, 'registration/register.html', context)


# Admin-only vendor-admin creation
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


@ratelimit(key='ip', rate='5/m', method='POST')  # 5 attempts per minute
def tenant_login(request):
    vendorInfo = Vendor.objects.prefetch_related('name')
    tenant = getattr(request, 'tenant', None)    
    if request.method == 'POST':
        form = TenantAuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()

            # 1️⃣ Platform Admin: global access
            if getattr(user, 'is_platform_admin', False):
                login(request, user)
                messages.success(request, f"Welcome back, {user.first_name}")
                return redirect(reverse('dashboard'))

            # 2️⃣ Tenant validation
            if not tenant:
                messages.error(request, "No tenant could be resolved. Access denied.")
                return redirect(reverse('no_tenant'))

            if not user.vendor or user.vendor.internal_id != tenant.internal_id:
                messages.error(request, "This account does not belong to this tenant.")
                return redirect(reverse('login'))

            # 3️⃣ Tenant-bound login successful
            login(request, user)
            messages.success(request, f"Welcome, {user.email}")

            # 4️⃣ Role-based redirection
            if user.role in ['vendor_admin', 'lab_staff']:
                return redirect(reverse('labs:vendor_dashboard'))
            elif user.role == 'patient':
                return redirect(reverse('labs:patient_dashboard'))
            elif user.role == 'clinician':
                return redirect(reverse('labs:clinician_dashboard'))
            else:
                # fallback route for unknown roles
                return redirect(reverse('login'))
    else:
        form = TenantAuthenticationForm(request)

    context = {
        'form': form,
        'tenant': tenant,
        'vendorInfo': vendorInfo,
    }
    # return render(request, 'platform/pages/login.html', context)
    return render(request, 'authentication/login.html', context)

def tenant_logout(request):
    logout(request)
    messages.info(request, "You have been logged out successfully.")
    return redirect(reverse_lazy('login'))

"""
    Tasks to complete:
    Password Resetting...
"""
# apps/accounts/views.py
from django.contrib.auth import views as auth_views

@ratelimit(key='ip', rate='3/h', method='POST')  # 3 password resets per hour
class TenantPasswordResetView(auth_views.PasswordResetView):
    """
    Custom password reset view that injects tenant into the form.
    """
    template_name = 'registration/password_reset_form.html'
    email_template_name = 'registration/password_reset_email.html'
    subject_template_name = 'registration/password_reset_subject.txt'
    form_class = TenantPasswordResetForm
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['tenant'] = getattr(self.request, 'tenant', None)
        return kwargs
    
    def form_valid(self, form):
        """
        Add extra context for better user experience.
        """
        tenant = getattr(self.request, 'tenant', None)
        if tenant:
            messages.info(
                self.request,
                f"If your email is registered with {tenant.name}, you'll receive reset instructions."
            )
        return super().form_valid(form)

"""