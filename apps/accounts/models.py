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
    """
    Core User model for Platform + Laboratory Information Management System (LIMS).

    RULES:
    - A user has exactly ONE canonical role.
    - Aliases are UI-only and never used for authorization.
    - Hierarchy is enforced through permission helpers.
    """

    # =====================================
    # ROLE DEFINITIONS (CANONICAL)
    # =====================================

    ROLE_CHOICES = [
        # --------- PLATFORM -------------
        ('platform_admin', 'Platform Administrator'),

        # -------- LABORATORY CORE --------
        ('vendor_admin', 'Lab Director / Super Admin'),
        ('lab_manager', 'Lab Manager / Supervisor'),
        ('scientist', 'Scientist / Pathologist / MLS'),
        ('technologist', 'Technologist / Phlebotomist'),
        ('logistics', 'Logistics Officer / Sample Collector'),
        ('receptionist', 'Receptionist / Front Desk'),

        # ------------ EXTENDED -------------
        ('clinician', 'Clinician'),
        ('patient', 'Patient'),
        ('learner', 'Learner'),
        ('facilitator', 'Facilitator'),
    ]

    # =====================================
    # CORE IDENTITY FIELDS
    # =====================================

    # email = models.EmailField()
    email = models.EmailField(unique=True) # Add unique=True
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    contact_number = PhoneNumberField(blank=True, null=True)

    vendor = models.ForeignKey(Vendor, null=True, blank=True, on_delete=models.SET_NULL, related_name='users')

    role = models.CharField(max_length=32, choices=ROLE_CHOICES)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = CustomUserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    class Meta:
        unique_together = [['email', 'vendor']]
        verbose_name = 'User'
        verbose_name_plural = 'Users'

    # Suppress Django warning for non-unique USERNAME_FIELD
    @classmethod
    def check(cls, **kwargs):
        errors = super().check(**kwargs)
        return [e for e in errors if e.id != 'auth.W004']

    # ========================================
    # LABORATORY ROLE HIERARCHY (AUTHORITATIVE)
    # ========================================

    LAB_HIERARCHY = [
        'receptionist',
        'logistics',
        'technologist',
        'scientist',
        'lab_manager',
        'vendor_admin',
    ]

    def role_at_least(self, role_name: str) -> bool:
        """
        Check whether user role is >= another role in the lab hierarchy.
        """
        if self.is_superuser or self.role == 'platform_admin':
            return True

        if self.role not in self.LAB_HIERARCHY:
            return False

        if role_name not in self.LAB_HIERARCHY:
            return False

        return self.LAB_HIERARCHY.index(self.role) >= self.LAB_HIERARCHY.index(role_name)

    # ============================================================
    # ROLE IDENTITY HELPERS
    # ============================================================

    @property
    def is_platform_admin(self):
        return self.is_superuser or self.role == 'platform_admin'

    @property
    def is_vendor_admin(self):
        return self.role == 'vendor_admin' or self.is_platform_admin

    @property
    def is_lab_manager(self):
        return self.role == 'lab_manager' or self.is_vendor_admin

    @property
    def is_scientist(self):
        return self.role == 'scientist' or self.role_at_least('scientist')

    @property
    def is_technologist(self):
        return self.role == 'technologist' or self.role_at_least('technologist')

    @property
    def is_logistics(self):
        return self.role == 'logistics'

    @property
    def is_receptionist(self):
        return self.role == 'receptionist'

    @property
    def is_clinician(self):
        return self.role == 'clinician'

    @property
    def is_patient(self):
        return self.role == 'patient'

    # =========================================
    # SAMPLE & ACCESSIONING
    # ========================================

    @property
    def can_collect_sample(self):
        return self.role in ['scientist', 'technologist', 'logistics'] or self.is_vendor_admin

    @property
    def can_accession_samples(self):
        return self.role in ['technologist', 'logistics'] or self.role_at_least('technologist')

    @property
    def can_track_sample_quality(self):
        return self.role == 'technologist' or self.role_at_least('technologist')

    @property
    def can_verify_sample(self):
        """
        Scientists & Technologists may enter results.
        Lab Managers are explicitly excluded.
        """
        return self.role in ['scientist', 'technologist'] or self.is_vendor_admin

    # =========================================
    # TEST REQUEST
    # ========================================
    @property
    def can_manage_request(self):
        return self.role in ['technologist', 'scientist', 'lab_manager'] or self.is_vendor_admin


    # =======================================
    # RESULT LIFECYCLE PERMISSIONS (CRITICAL)
    # ========================================

    @property
    def can_enter_results(self):
        """
        Scientists & Technologists may enter results.
        Lab Managers are explicitly excluded.
        """
        return self.role in ['scientist', 'technologist'] or self.is_vendor_admin

    @property
    def can_verify_results(self):
        """
        Lab Manager / Supervisor core responsibility.
        Verification before release.
        """
        return self.role == 'lab_manager' or self.is_vendor_admin

    @property
    def can_release_results(self):
        """
        Scientist/Pathologist/MLS core responsibility.
        Final legal release of results.
        """
        return self.role == 'scientist' or self.is_vendor_admin

    @property
    def can_amend_results(self):
        """
        Post-release amendment (restricted & auditable).
        """
        return self.is_vendor_admin or self.has_perm('labs.can_amend_results')

    # ========================================
    # PATIENT
    # =========================================

    @property
    def can_register_patients(self):
        return self.role in ['receptionist', 'logistics'] or self.is_vendor_admin

    # ========================================
    # BILLING
    # =========================================
    
    @property
    def can_manage_billing(self):
        return self.role == 'receptionist' or self.is_vendor_admin

    @property
    def can_authorize_billing(self):
        "Can proceed without payment but debet remains"
        return self.role in ['lab_manager', 'vendor_admin', 'scientist']

    @property
    def can_waive_billing(self):
        return self.role in ['lab_manager', 'vendor_admin', 'scientist']

    @property
    def can_receive_payment(self):
        return self.role in ['lab_manager', 'vendor_admin', 'scientist']

    @property
    def can_download_results(self):
        return self.role in ['receptionist', 'clinician'] or self.is_vendor_admin

    # ===================================
    # ADMINISTRATIVE
    # ====================================

    @property
    def can_manage_inventory(self):
        return self.role_at_least('lab_manager')

    @property
    def can_manage_staff(self):
        return self.role in ['lab_manager', 'vendor_admin']

    # ===============================
    # APPOINTMENT
    # ==============================
    @property
    def can_manage_appointment(self):
        """
        Full control: create templates, generate slots, edit/delete slots.
        """
        return self.role in ['lab_manager', 'vendor_admin']

    @property
    def can_view_appointment(self):
        """
        Read-only visibility of appointments and slots.
        """
        return self.can_manage_appointment or self.role == 'receptionist'

    # ==============================
    # DISPLAY & DEBUGGING
    # ================================

    def get_full_name(self):
        full_name = f"{self.first_name} {self.last_name}".strip()
        return full_name if full_name else self.email
    
    def get_short_name(self):
        short_name = f"{self.last_name}".strip()
        return short_name if short_name else self.get_full_name()


    def get_role_display_name(self):
        return dict(self.ROLE_CHOICES).get(self.role, 'User')

    def get_permissions_summary(self):
        """
        Human-readable permission snapshot (useful for debugging & audits).
        """
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
        if self.can_manage_inventory:
            permissions.append('Manage Inventory')
        if self.can_accession_samples:
            permissions.append('Accession Samples')
        if self.can_register_patients:
            permissions.append('Register Patients')

        return permissions

    def __str__(self):
        return f"{self.get_full_name()} — {self.get_role_display_name()}"


class BaseProfile(models.Model):
    logo = models.ImageField(upload_to='logos/', blank=True, null=True, help_text="Company Logo!")
    director_signature = models.ImageField(upload_to='signatures/', blank=True, null=True, help_text="Director's Signature")
    company_seal = models.ImageField(upload_to='seals/', blank=True, null=True, help_text="Company Seal")
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

    # Bank Payment details
    bank_account = models.CharField(max_length=11, blank=True, null=True, default="bank")
    bank_name = models.CharField(max_length=200, blank=True, null=True, default="bank")      
    bank_account_name = models.CharField(max_length=200, blank=True, null=True, default="bank")      
    
    # Payment Gateway Settings and Credentials
    paystack_enabled = models.BooleanField(default=False)
    paystack_public_key = models.CharField(max_length=100, blank=True, null=True)
    paystack_secret_key = models.CharField(max_length=100, blank=True, null=True)
    
    # Alternative: Flutterwave
    flutterwave_enabled = models.BooleanField(default=False)
    flutterwave_public_key = models.CharField(max_length=100, blank=True, null=True)
    flutterwave_secret_key = models.CharField(max_length=100, blank=True, null=True)
    
    # General payment settings
    require_payment_before_sample_verification = models.BooleanField(default=True)
    allow_partial_payments = models.BooleanField(default=False)

    def __str__(self):
        return f"Profile of {self.vendor.name}"

    def save(self, *args, **kwargs):
        if self.office_address and self.office_city_state and self.office_country:
            full_address = f"{self.office_address}, {self.office_city_state}, {self.office_country}, {self.office_zipcode}"
        super().save(*args, **kwargs)


    # def save(self, *args, **kwargs):
    #     if self.office_address and self.office_city_state and self.office_country:
    #         full_address = f"{self.office_address}, {self.office_city_state}, {self.office_country}, {self.office_zipcode}"
    #         # try:
    #             geolocator = Nominatim(user_agent="firstjp_lims")
    #             location = geolocator.geocode(full_address)
    #             if location:
    #                 self.latitude = location.latitude
    #                 self.longitude = location.longitude
    #         except Exception:
    #             # Silently fail if geocoding doesn't work
    #             pass
    #     super().save(*args, **kwargs)

