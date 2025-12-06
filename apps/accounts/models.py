from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone
from apps.tenants.models import Vendor
from phonenumber_field.modelfields import PhoneNumberField
# from geopy.geocoders import Nominatim
import uuid
from django.db import transaction

# apps/accounts/models.py

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
    

# # Custom User Management 
# class CustomUserManager(BaseUserManager):
#     def _create_user(self, email, password, **extra_fields):
#         if not email:
#             raise ValueError('Email must be set')
#         user = self.model(email=self.normalize_email(email), **extra_fields)
#         user.set_password(password)
#         user.save(using=self._db)
#         return user

#     def create_user(self, email, password=None, **extra_fields):
#         extra_fields.setdefault('is_staff', False)
#         extra_fields.setdefault('is_superuser', False)
#         return self._create_user(email, password, **extra_fields)
    
#     def create_superuser(self, email, password, **extra_fields):
#         extra_fields.setdefault('is_staff', True)
#         extra_fields.setdefault('is_superuser', True)
#         if extra_fields.get('is_staff') is not True:
#             raise ValueError('Superuser must have is_staff=True')
#         if extra_fields.get('is_superuser') is not True:
#             raise ValueError('Superuser must have is_superuser=True')
#         return self._create_user(email, password, **extra_fields)


# User setup   
class User(AbstractBaseUser, PermissionsMixin):
    ROLE_CHOICES = [
        ('platform_admin', 'Platform Admin'),
        ('vendor_admin', 'Vendor Admin'),
        ('lab_staff', 'Lab Staff'),
        ('clinician', 'Clinician'),
        ('patient', 'Patient'),
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






























# # apps/accounts/models.py
# import uuid
# from django.db import models
# from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
# from django.utils import timezone
# from django.core.validators import validate_email
# from django.utils.translation import gettext_lazy as _
# from phonenumber_field.modelfields import PhoneNumberField
# from apps.tenants.models import Vendor


# class CustomUserManager(BaseUserManager):
#     use_in_migrations = True

#     def _create_user(self, email, password, vendor=None, **extra_fields):
#         if not email:
#             raise ValueError("Email must be set")

#         email = self.normalize_email(email)
#         validate_email(email)

#         user = self.model(email=email, **extra_fields)
#         user.set_password(password)
#         user.save(using=self._db)
#         return user

#     def create_user(self, email, password=None, vendor=None, **extra_fields):
#         extra_fields.setdefault("is_staff", False)
#         extra_fields.setdefault("is_superuser", False)
#         extra_fields.setdefault("role", User.ROLE_PATIENT)
#         return self._create_user(email, password, **extra_fields)

#     def create_superuser(self, email, password=None, vendor=None, **extra_fields):
#         extra_fields.setdefault("is_staff", True)
#         extra_fields.setdefault("is_superuser", True)
#         extra_fields.setdefault("role", User.ROLE_PLATFORM)

#         return self._create_user(email, password, **extra_fields)


# class User(AbstractBaseUser, PermissionsMixin):
#     """GLOBAL PLATFORM USER — used across all tenants and LMS."""
    
#     # Global roles
#     ROLE_PLATFORM = 'platform_admin'
#     ROLE_STUDENT = 'student'
#     ROLE_FACILITATOR = 'facilitator'
#     ROLE_GENERAL = 'general'     # default non-tenant role
#     ROLE_PATIENT = 'patient'     # global indicator (but main roles done per tenant)

#     ROLE_CHOICES = [
#         (ROLE_PLATFORM, "Platform Admin"),
#         (ROLE_STUDENT, "Student"),
#         (ROLE_FACILITATOR, "Facilitator"),
#         (ROLE_GENERAL, "General User"),
#         (ROLE_PATIENT, "Patient (global)"),
#     ]

#     id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
#     email = models.EmailField(_("Email Address"), unique=True)
#     first_name = models.CharField(max_length=150, blank=True)
#     last_name = models.CharField(max_length=150, blank=True)
#     contact_number = PhoneNumberField(blank=True, null=True)

#     role = models.CharField(max_length=32, choices=ROLE_CHOICES, default=ROLE_GENERAL)

#     is_active = models.BooleanField(default=True)
#     is_staff = models.BooleanField(default=False)
#     date_joined = models.DateTimeField(default=timezone.now)

#     USERNAME_FIELD = 'email'
#     REQUIRED_FIELDS = []

#     objects = CustomUserManager()

#     def __str__(self):
#         return f"{self.email}"

#     @property
#     def is_platform_admin(self):
#         return self.is_superuser or self.role == self.ROLE_PLATFORM


# class UserTenantMembership(models.Model):
#     """Maps a global user to a tenant (vendor) with a tenant-specific role."""

#     ROLE_VENDOR_ADMIN = 'vendor_admin'
#     ROLE_LAB_STAFF = 'lab_staff'
#     ROLE_CLINICIAN = 'clinician'
#     ROLE_PATIENT = 'patient'

#     TENANT_ROLE_CHOICES = [
#         (ROLE_VENDOR_ADMIN, "Vendor Admin"),
#         (ROLE_LAB_STAFF, "Lab Staff"),
#         (ROLE_CLINICIAN, "Clinician"),
#         (ROLE_PATIENT, "Patient"),
#     ]

#     id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

#     user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="memberships")
#     vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="memberships")
#     role = models.CharField(max_length=50, choices=TENANT_ROLE_CHOICES)

#     date_joined = models.DateTimeField(auto_now_add=True)
#     is_active = models.BooleanField(default=True)

#     class Meta:
#         unique_together = ('user', 'vendor')  # one membership per vendor per user

#     def __str__(self):
#         return f"{self.user.email} → {self.vendor.name} ({self.role})"



# class BaseProfile(models.Model):
#     logo = models.ImageField(upload_to='logos/', blank=True, null=True, help_text="Company Logo!")
#     office_address = models.TextField(blank=True, help_text="e.g. - 42, Awolowo Road, Old-Bodija")
#     office_city_state = models.CharField(max_length=100, blank=True, help_text="Victoria-Island, Lagos")
#     office_country = models.CharField(max_length=100, blank=True, help_text="Nigeria")
#     office_zipcode = models.CharField(max_length=20, blank=True, help_text="200200")
#     latitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True, help_text="23.56")
#     longitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True, help_text="23.56")
#     created_at = models.DateTimeField(auto_now_add=True)
#     updated_at = models.DateTimeField(auto_now=True)

#     class Meta:
#         abstract = True

#     @property
#     def is_complete(self):
#         return all([
#             self.entity_img,
#             self.office_address,
#             self.office_city_state,
#             self.office_country,
#             self.office_zipcode,
#         ])


# class VendorProfile(BaseProfile):
#     vendor = models.OneToOneField(Vendor, on_delete=models.CASCADE, related_name='profile')
#     registration_number = models.CharField(max_length=100, blank=True, null=True)
#     contact_number = PhoneNumberField(blank=True, null=True)

#     def __str__(self):
#         return f"Profile of {self.vendor.name}"

#     def save(self, *args, **kwargs):
#         if self.office_address and self.office_city_state and self.office_country:
#             full_address = f"{self.office_address}, {self.office_city_state}, {self.office_country}, {self.office_zipcode}"
#             # try:
#             #     geolocator = Nominatim(user_agent="firstjp_lims")
#             #     location = geolocator.geocode(full_address)
#             #     if location:
#             #         self.latitude = location.latitude
#             #         self.longitude = location.longitude
#             # except Exception:
#             #     # Silently fail if geocoding doesn't work
#             #     pass
#         super().save(*args, **kwargs)







# """
# UNIQUE VENDOR SETUP
# """
# # from django.db import models
# # from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
# # from django.utils import timezone
# # from apps.tenants.models import Vendor
# # from phonenumber_field.modelfields import PhoneNumberField
# # # from geopy.geocoders import Nominatim
# # import uuid
# # from django.db import transaction

# # # Custom User Management 
# # class CustomUserManager(BaseUserManager):
# #     def _create_user(self, email, password, **extra_fields):
# #         if not email:
# #             raise ValueError('Email must be set')
# #         user = self.model(email=self.normalize_email(email), **extra_fields)
# #         user.set_password(password)
# #         user.save(using=self._db)
# #         return user

# #     def create_user(self, email, password=None, **extra_fields):
# #         extra_fields.setdefault('is_staff', False)
# #         extra_fields.setdefault('is_superuser', False)
# #         return self._create_user(email, password, **extra_fields)
    
# #     def create_superuser(self, email, password, **extra_fields):
# #         extra_fields.setdefault('is_staff', True)
# #         extra_fields.setdefault('is_superuser', True)
# #         if extra_fields.get('is_staff') is not True:
# #             raise ValueError('Superuser must have is_staff=True')
# #         if extra_fields.get('is_superuser') is not True:
# #             raise ValueError('Superuser must have is_superuser=True')
# #         return self._create_user(email, password, **extra_fields)


# # # User setup   
# # class User(AbstractBaseUser, PermissionsMixin):
# #     ROLE_CHOICES = [
# #         ('platform_admin', 'Platform Admin'),
# #         ('vendor_admin', 'Vendor Admin'),
# #         ('lab_staff', 'Lab Staff'),
# #         ('clinician', 'Clinician'),
# #         ('patient', 'Patient'),
# #     ]

# #     email = models.EmailField(unique=True)
# #     first_name = models.CharField(max_length=150, blank=True)
# #     last_name = models.CharField(max_length=150, blank=True)
# #     contact_number = PhoneNumberField(blank=True, null=True)
# #     vendor = models.ForeignKey(Vendor, null=True, blank=True, on_delete=models.SET_NULL)
# #     role = models.CharField(max_length=32, choices=ROLE_CHOICES, default='lab_staff')
# #     is_active = models.BooleanField(default=True)
# #     is_staff = models.BooleanField(default=False)
# #     date_joined = models.DateTimeField(default=timezone.now)

# #     objects = CustomUserManager()

# #     USERNAME_FIELD = 'email'
# #     REQUIRED_FIELDS = []


# #     @property
# #     def is_platform_admin(self):
# #         return self.is_superuser or self.role == 'platform_admin'

# #     def __str__(self):
# #         return f"{self.first_name} ({self.email}) is a/an {self.role}"



# # class BaseProfile(models.Model):
# #     logo = models.ImageField(upload_to='logos/', blank=True, null=True, help_text="Company Logo!")
# #     office_address = models.TextField(blank=True, help_text="e.g. - 42, Awolowo Road, Old-Bodija")
# #     office_city_state = models.CharField(max_length=100, blank=True, help_text="Victoria-Island, Lagos")
# #     office_country = models.CharField(max_length=100, blank=True, help_text="Nigeria")
# #     office_zipcode = models.CharField(max_length=20, blank=True, help_text="200200")
# #     latitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True, help_text="23.56")
# #     longitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True, help_text="23.56")
# #     created_at = models.DateTimeField(auto_now_add=True)
# #     updated_at = models.DateTimeField(auto_now=True)

# #     class Meta:
# #         abstract = True

# #     @property
# #     def is_complete(self):
# #         return all([
# #             self.entity_img,
# #             self.office_address,
# #             self.office_city_state,
# #             self.office_country,
# #             self.office_zipcode,
# #         ])


# # class VendorProfile(BaseProfile):
# #     vendor = models.OneToOneField(Vendor, on_delete=models.CASCADE, related_name='profile')
# #     registration_number = models.CharField(max_length=100, blank=True, null=True)
# #     contact_number = PhoneNumberField(blank=True, null=True)

# #     def __str__(self):
# #         return f"Profile of {self.vendor.name}"

# #     def save(self, *args, **kwargs):
# #         if self.office_address and self.office_city_state and self.office_country:
# #             full_address = f"{self.office_address}, {self.office_city_state}, {self.office_country}, {self.office_zipcode}"
# #             # try:
# #             #     geolocator = Nominatim(user_agent="firstjp_lims")
# #             #     location = geolocator.geocode(full_address)
# #             #     if location:
# #             #         self.latitude = location.latitude
# #             #         self.longitude = location.longitude
# #             # except Exception:
# #             #     # Silently fail if geocoding doesn't work
# #             #     pass
# #         super().save(*args, **kwargs)

