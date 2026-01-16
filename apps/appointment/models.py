import logging
import pytz
from datetime import timedelta
from collections import defaultdict

from django.db import models
from django.conf import settings
from apps.labs.utils import get_next_sequence
from django.utils import timezone
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
# Visitor/Walk-in Patient (Unauthenticated)
from django.db import models
from django.utils import timezone

from apps.labs.utils import get_next_sequence


logger = logging.getLogger(__name__)


class AppointmentSlotQuerySet(models.QuerySet):
    def available_for_vendor(self, vendor, start_date=None, days=30):
        if not vendor:
            return self.none()

        if not start_date:
            start_date = timezone.now().date()

        end_date = start_date + timedelta(days=days)

        return (
            self.filter(
                vendor=vendor,
                is_active=True,
                date__range=(start_date, end_date),
                current_bookings__lt=models.F('max_appointments')
            )
            .order_by('date', 'start_time')
        )


class AppointmentSlot(models.Model):
    """
    Represents a single bookable time window at a laboratory.
    """

    vendor = models.ForeignKey(
        'tenants.Vendor',
        on_delete=models.CASCADE,
        related_name='appointment_slots'
    )

    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()

    max_appointments = models.PositiveIntegerField(default=1)
    current_bookings = models.PositiveIntegerField(default=0)

    slot_type = models.CharField(
        max_length=20,
        choices=[
            ('sample_collection', 'Sample Collection'),
            ('consultation', 'Consultation'),
            ('result_discussion', 'Result Discussion'),
            ('general', 'General Visit'),
        ],
        default='consultation'
    )
    objects = AppointmentSlotQuerySet.as_manager()

    instructions = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['date', 'start_time']
        indexes = [
            models.Index(fields=['vendor', 'date', 'is_active']),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(current_bookings__lte=models.F('max_appointments')),
                name='slot_capacity_not_exceeded'
            )
        ]

    # -----------------
    # VALIDATION
    # -----------------
    def clean(self):
        if self.end_time <= self.start_time:
            raise ValidationError("End time must be after start time.")

        # Prevent overlapping slots per vendor/day
        overlapping = AppointmentSlot.objects.filter(
            vendor=self.vendor,
            date=self.date,
            start_time__lt=self.end_time,
            end_time__gt=self.start_time
        ).exclude(pk=self.pk)

        if overlapping.exists():
            raise ValidationError("This slot overlaps with an existing slot.")

    # -----------------
    # BUSINESS LOGIC
    # -----------------
    def _slot_datetime(self):
        vendor_tz = pytz.timezone(self.vendor.timezone)
        naive = timezone.datetime.combine(self.date, self.start_time)
        return vendor_tz.localize(naive)

    @property
    def is_past(self):
        return self._slot_datetime() <= timezone.now()

    @property
    def is_available(self):
        return (
            self.is_active
            and not self.is_past
            and self.current_bookings < self.max_appointments
        )

    def recalculate_bookings(self):
        """Safety repair for denormalized count."""
        self.current_bookings = self.appointments.exclude(
            status='cancelled'
        ).count()
        self.save(update_fields=['current_bookings'])

    @staticmethod
    def group_by_date(slots):
        """
        Group appointment slots by date.
        Returns: { date: [slot, slot, ...] }
        """
        grouped = defaultdict(list)
        for slot in slots:
            grouped[slot.date].append(slot)
        return dict(grouped)
    
    def __str__(self):
        return f"{self.date} {self.start_time}-{self.end_time}"


class Appointment(models.Model):
    """
    Patient appointment booking.
    """

    STATUS_PENDING = 'pending'
    STATUS_CONFIRMED = 'confirmed'
    STATUS_CANCELLED = 'cancelled'
    STATUS_COMPLETED = 'completed'
    STATUS_NO_SHOW = 'no_show'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_CONFIRMED, 'Confirmed'),
        (STATUS_CANCELLED, 'Cancelled'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_NO_SHOW, 'No Show'),
    ]

    VALID_TRANSITIONS = {
        STATUS_PENDING: [STATUS_CONFIRMED, STATUS_CANCELLED],
        STATUS_CONFIRMED: [STATUS_COMPLETED, STATUS_NO_SHOW, STATUS_CANCELLED],
    }

    vendor = models.ForeignKey(
        'tenants.Vendor',
        on_delete=models.CASCADE,
        related_name='appointments'
    )

    appointment_id = models.CharField(max_length=20, unique=True)

    patient = models.ForeignKey(
        'labs.Patient',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='appointments'
    )

    slot = models.ForeignKey(
        AppointmentSlot,
        on_delete=models.PROTECT,
        related_name='appointments'
    )

    appointment_type = models.CharField(
        max_length=20,
        choices=[
            ('sample_collection', 'Sample Collection'),
            ('consultation', 'Consultation'),
            ('result_discussion', 'Result Discussion'),
            ('test_request', 'New Test Request'),
        ],
        default='consultation'
    )

    test_request = models.OneToOneField(
        'labs.TestRequest',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='appointment'
    )

    # Additional info
    reason_for_visit = models.TextField(blank=True, help_text="Patient's notes about the visit")
    special_requirements = models.TextField(blank=True, help_text="Any special needs (wheelchair access, etc.)")

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING
    )

    booked_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='booked_appointments'
    )


    confirmed_at = models.DateTimeField(null=True, blank=True)
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='confirmed_appointments'
    )

    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='cancelled_appointments'
    )
    cancellation_reason = models.TextField(blank=True)

    confirmation_sent = models.BooleanField(default=False)
    reminder_sent = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['vendor', 'status']),
            models.Index(fields=['appointment_id']),
        ]

    # -----------------
    # VALIDATION
    # -----------------
    def clean(self):
        if self.slot.vendor_id != self.vendor_id:
            raise ValidationError("Slot does not belong to this laboratory.")

    # -----------------
    # STATE MANAGEMENT
    # -----------------
    def transition(self, new_status, user=None, reason=None):
        allowed = self.VALID_TRANSITIONS.get(self.status, [])
        if new_status not in allowed:
            raise ValidationError(
                f"Cannot change status from {self.status} to {new_status}"
            )

        self.status = new_status

        if new_status == self.STATUS_CONFIRMED:
            self.confirmed_at = timezone.now()
            self.confirmed_by = user

        if new_status == self.STATUS_CANCELLED:
            self.cancelled_at = timezone.now()
            self.cancelled_by = user
            self.cancellation_reason = reason or ""

        self.save()

    # -----------------
    # DOMAIN ACTIONS
    # -----------------
    def confirm(self, user):
        self.transition(
            new_status=self.STATUS_CONFIRMED,
            user=user
        )

    def cancel(self, reason=None, cancelled_by_user=None):
        self.transition(
            new_status=self.STATUS_CANCELLED,
            user=cancelled_by_user,
            reason=reason
        )
        
    # -----------------
    # SAVE
    # -----------------
    def save(self, *args, **kwargs):
        if not self.appointment_id:
            self.appointment_id = get_next_sequence("APT", vendor=self.vendor)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.appointment_id} ({self.status})"


class AppointmentSlotTemplate(models.Model):
    """
    Templates for recurring appointment slots.
    Staff creates these once, then generates actual slots in bulk.
    """
    vendor = models.ForeignKey('tenants.Vendor', on_delete=models.CASCADE, related_name='slot_templates')
    
    name = models.CharField(max_length=100, help_text="Template name (e.g., 'Consultation')")
    
    # Time configuration
    start_time = models.TimeField(help_text="Slot start time")
    end_time = models.TimeField(help_text="Slot end time")
    duration_minutes = models.PositiveIntegerField(default=30, help_text="Slot duration in minutes")
    
    # Recurrence pattern
    RECURRENCE_CHOICES = [
        ('weekdays', 'Weekdays (Mon-Fri)'),
        ('weekends', 'Weekends (Sat-Sun)'),
        ('daily', 'Daily'),
        ('specific_days', 'Specific Days of Week'),
    ]
    recurrence_pattern = models.CharField(max_length=20, choices=RECURRENCE_CHOICES, default='weekdays')
    
    # Specific days (if recurrence_pattern = 'specific_days')
    monday = models.BooleanField(default=False)
    tuesday = models.BooleanField(default=False)
    wednesday = models.BooleanField(default=False)
    thursday = models.BooleanField(default=False)
    friday = models.BooleanField(default=False)
    saturday = models.BooleanField(default=False)
    sunday = models.BooleanField(default=False)
    
    # Capacity
    max_appointments = models.PositiveIntegerField(default=1, help_text="Max bookings per slot")
    slot_type = models.CharField(
        max_length=20,
        choices=[
            ('sample_collection', 'Sample Collection'),
            ('consultation', 'Consultation'),
            ('result_discussion', 'Result Discussion'),
            ('general', 'General Visit'),
        ],
        default='consultation'
    )
    instructions = models.TextField(
        blank=True,
        null=True, 
        help_text="Prep instructions (e.g., 'Fasting required for 12 hours')"
    )
    # Status
    is_active = models.BooleanField(default=True)
    
    # Metadata
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_slot_templates'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['start_time']
        
    def __str__(self):
        return f"{self.name} ({self.start_time}-{self.end_time})"
    
    def get_active_days(self):
        """Return list of active weekday numbers (0=Monday, 6=Sunday)."""
        if self.recurrence_pattern == 'weekdays':
            return [0, 1, 2, 3, 4]  # Mon-Fri
        elif self.recurrence_pattern == 'weekends':
            return [5, 6]  # Sat-Sun
        elif self.recurrence_pattern == 'daily':
            return list(range(7))
        elif self.recurrence_pattern == 'specific_days':
            days = []
            day_map = [
                (self.monday, 0),
                (self.tuesday, 1),
                (self.wednesday, 2),
                (self.thursday, 3),
                (self.friday, 4),
                (self.saturday, 5),
                (self.sunday, 6),
            ]
            return [day_num for is_active, day_num in day_map if is_active]
        return []

    def generate_slots(self, start_date, end_date):
        from datetime import timedelta

        slots_created = 0
        current_date = start_date
        active_days = self.get_active_days()

        while current_date <= end_date:
            if current_date.weekday() in active_days:
                AppointmentSlot.objects.get_or_create(
                    vendor=self.vendor,
                    date=current_date,
                    start_time=self.start_time,
                    end_time=self.end_time,
                    defaults={
                        'max_appointments': self.max_appointments,
                        'slot_type': self.slot_type,
                        'instructions': self.instructions,
                        'is_active': True,
                    }
                )
                slots_created += 1

            current_date += timedelta(days=1)

        return slots_created


