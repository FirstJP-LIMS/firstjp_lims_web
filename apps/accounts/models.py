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
    
class User(AbstractBaseUser, PermissionsMixin):
    ROLE_CHOICES = [
        ('platform_admin', 'Platform Admin'),
        # laboratory roles - hierarchical
        ('vendor_admin', 'Vendor Admin'),
        ('pathologist', 'Pathologist'),
        ('lab_supervisor', 'Lab Supervisor'),
        ('lab_technician', 'Lab Technician'),
        ('lab_manager', 'Lab Manager'),
        ('lab_staff', 'Lab Staff'),
        # laboratory extended roles
        ('clinician', 'Clinician'),
        ('patient', 'Patient'),
        ('receptionist', 'Receptionist'),
        
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

    # Suppress W004 warning about non-unique USERNAME_FIELD
    @classmethod
    def check(cls, **kwargs):
        errors = super().check(**kwargs)
        errors = [e for e in errors if e.id != 'auth.W004']
        return errors
    
    # ============================================================
    # PLATFORM & VENDOR ROLES
    # ============================================================
    
    @property
    def is_platform_admin(self):
        """Platform-wide administrator (highest level)"""
        return self.is_superuser or self.role == 'platform_admin'

    @property
    def is_vendor_admin(self):
        """Vendor/Laboratory administrator"""
        return self.role == 'vendor_admin' or self.is_superuser
    
    # ============================================================
    # LABORATORY HIERARCHICAL ROLES
    # ============================================================
    
    @property
    def is_pathologist(self):
        """
        Pathologist - Can release verified results to patients/doctors.
        Third highest level in lab hierarchy.
        """
        return self.role in ['pathologist', 'vendor_admin', 'platform_admin'] or self.is_superuser
    
    @property
    def is_lab_supervisor(self):
        """
        Lab Supervisor - Can verify results entered by technicians.
        Includes pathologist and higher roles.
        """
        return self.role in [
            'lab_supervisor', 
            'pathologist', 
            'lab_manager',
            'vendor_admin', 
            'platform_admin'
        ] or self.is_superuser
    
    @property
    def is_lab_technician(self):
        """
        Lab Technician - Can enter and edit test results (before verification).
        Includes all higher laboratory roles.
        """
        return self.role in [
            'lab_technician',
            'lab_supervisor',
            'pathologist',
            'lab_manager',
            'lab_staff',
            'vendor_admin',
            'platform_admin'
        ] or self.is_superuser
    
    @property
    def is_lab_staff(self):
        """
        General lab staff - Can view results and perform basic operations.
        Includes all laboratory personnel.
        """
        return self.role in [
            'lab_staff',
            'lab_technician',
            'lab_supervisor',
            'pathologist',
            'lab_manager',
            'vendor_admin',
            'platform_admin'
        ] or self.is_superuser
    
    @property
    def is_lab_manager(self):
        """
        Lab Manager - Has administrative oversight, can manage staff and operations.
        """
        return self.role in ['lab_manager', 'vendor_admin', 'platform_admin'] or self.is_superuser
    
    # ============================================================
    # EXTENDED ROLES
    # ============================================================
    
    @property
    def is_clinician(self):
        """Clinician - Can order tests and view results"""
        return self.role == 'clinician'
    
    @property
    def is_patient(self):
        """Patient - Can view own results"""
        return self.role == 'patient'
    
    @property
    def is_receptionist(self):
        """Receptionist - Can register patients and create test requests"""
        return self.role == 'receptionist'
    
    # ============================================================
    # PERMISSION HELPERS
    # ============================================================
    
    @property
    def can_modify_inventory(self):
        """Check if user can create/edit/delete inventory items"""
        return self.role in [
            'platform_admin', 
            'vendor_admin', 
            'lab_manager',
            'lab_staff'
        ] or self.is_superuser
    
    @property
    def can_enter_results(self):
        """Check if user can enter test results"""
        return self.is_lab_technician
    
    @property
    def can_verify_results(self):
        """Check if user can verify test results"""
        return self.is_lab_supervisor
    
    @property
    def can_release_results(self):
        """Check if user can release results to patients/doctors"""
        return self.is_pathologist
    
    @property
    def can_amend_results(self):
        """Check if user can amend released results (restricted action)"""
        return self.is_vendor_admin or self.has_perm('laboratory.can_amend_results')
    
    @property
    def can_manage_staff(self):
        """Check if user can manage laboratory staff"""
        return self.is_lab_manager or self.is_vendor_admin
    
    @property
    def can_order_tests(self):
        """Check if user can order laboratory tests"""
        return self.is_clinician or self.is_receptionist or self.is_vendor_admin
    
    # ============================================================
    # DISPLAY METHODS
    # ============================================================
    
    def get_full_name(self):
        """Full name"""
        full_name = f"{self.first_name} {self.last_name}".strip()
        return full_name if full_name else self.email
    
    def get_role_display_name(self):
        """Get friendly display name for user's role"""
        role_display_map = {
            'platform_admin': 'Platform Administrator',
            'vendor_admin': 'Laboratory Administrator',
            'pathologist': 'Pathologist',
            'lab_supervisor': 'Laboratory Supervisor',
            'lab_technician': 'Laboratory Technician',
            'lab_manager': 'Laboratory Manager',
            'lab_staff': 'Laboratory Staff',
            'clinician': 'Clinician',
            'patient': 'Patient',
            'receptionist': 'Receptionist',
            'learner': 'Learner',
            'facilitator': 'Facilitator',
        }
        return role_display_map.get(self.role, 'User')
    
    def get_permissions_summary(self):
        """Get a summary of what this user can do (useful for debugging)"""
        permissions = []
        
        if self.can_enter_results:
            permissions.append('Enter Results')
        if self.can_verify_results:
            permissions.append('Verify Results')
        if self.can_release_results:
            permissions.append('Release Results')
        if self.can_amend_results:
            permissions.append('Amend Results')
        if self.can_manage_staff:
            permissions.append('Manage Staff')
        if self.can_order_tests:
            permissions.append('Order Tests')
        if self.can_modify_inventory:
            permissions.append('Manage Inventory')
        
        return permissions
    
    def __str__(self):
        return f"{self.get_full_name()} - {self.get_role_display_name()}"

# User setup   
# class User(AbstractBaseUser, PermissionsMixin):
#     ROLE_CHOICES = [
#         ('platform_admin', 'Platform Admin'),
#         # laboratory roles
#         ('vendor_admin', 'Vendor Admin'),
#         ('lab_manager', 'Lab Manager'),
#         ('lab_staff', 'Lab Staff'),
#         # laboratory extended roles
#         ('clinician', 'Clinician'),
#         ('patient', 'Patient'),
        
#         ('learner', 'Learner'), # Student
#         ('facilitator', 'Facilitator'),
#     ]

#     email = models.EmailField()
#     first_name = models.CharField(max_length=150, blank=True)
#     last_name = models.CharField(max_length=150, blank=True)
#     contact_number = PhoneNumberField(blank=True, null=True)
#     vendor = models.ForeignKey(Vendor, null=True, blank=True, on_delete=models.SET_NULL)
#     role = models.CharField(max_length=32, choices=ROLE_CHOICES, default='lab_staff')
#     is_active = models.BooleanField(default=True)
#     is_staff = models.BooleanField(default=False)
#     date_joined = models.DateTimeField(default=timezone.now)

#     objects = CustomUserManager()

#     USERNAME_FIELD = 'email'
#     REQUIRED_FIELDS = []

#     class Meta:
#         unique_together = [['email', 'vendor']] 

#     # Suppress W004 warning about non-unique USERNAME_FIELD
#     @classmethod
#     def check(cls, **kwargs):
#         errors = super().check(**kwargs)
#         errors = [e for e in errors if e.id != 'auth.W004']
#         return errors
    
#     # roles 
#     @property
#     def is_platform_admin(self):
#         return self.is_superuser or self.role == 'platform_admin'

#     @property
#     def is_vendor_admin(self):
#         return self.role == 'vendor_admin' or self.is_superuser
    
#     @property
#     def is_lab_staff(self):
#         return self.role == 'lab_staff'

#     @property
#     def can_modify_inventory(self):
#         """Check if user can create/edit/delete inventory items"""
#         return self.role in ['platform_admin', 'vendor_admin', 'lab_staff'] or self.is_superuser
    
#     def get_full_name(self):
#         """ Full name"""
#         full_name = f"{self.first_name} {self.last_name}".strip()
#         return full_name if full_name else self.email
    
#     def __str__(self):
#         return f"{self.first_name} - Role ({self.role})"


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

