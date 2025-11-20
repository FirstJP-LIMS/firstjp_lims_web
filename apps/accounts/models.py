from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone
from apps.tenants.models import Vendor
from phonenumber_field.modelfields import PhoneNumberField
# from geopy.geocoders import Nominatim
import uuid
from django.db import transaction


# Custom User Management 
class CustomUserManager(BaseUserManager):
    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError('Email must be set')
        user = self.model(email=self.normalize_email(email), **extra_fields)
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
            raise ValueError('Superuser must have is_staff=True')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True')
        return self._create_user(email, password, **extra_fields)


# User setup   
class User(AbstractBaseUser, PermissionsMixin):
    ROLE_CHOICES = [
        ('platform_admin', 'Platform Admin'),
        ('vendor_admin', 'Vendor Admin'),
        ('lab_staff', 'Lab Staff'),
        ('clinician', 'Clinician'),
        ('patient', 'Patient'),
    ]

    email = models.EmailField(unique=True)
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

    def __str__(self):
        return f"{self.first_name} ({self.email}) is a/an {self.role}"

    @property
    def is_platform_admin(self):
        return self.is_superuser or self.role == 'platform_admin'


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
            try:
                geolocator = Nominatim(user_agent="firstjp_lims")
                location = geolocator.geocode(full_address)
                if location:
                    self.latitude = location.latitude
                    self.longitude = location.longitude
            except Exception:
                # Silently fail if geocoding doesn't work
                pass
        super().save(*args, **kwargs)

