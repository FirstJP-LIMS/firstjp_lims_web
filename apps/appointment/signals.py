import logging
from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from .models import Appointment
from apps.notification.domain_events import DomainEvent
from apps.notification.engine import dispatch_event

logger = logging.getLogger(__name__)

@receiver(pre_save, sender=Appointment)
def capture_old_status(sender, instance, **kwargs):
    """Stores status before save to detect transitions."""
    if instance.pk:
        # Optimization: use .only() to reduce DB load
        instance._old_status = Appointment.objects.filter(pk=instance.pk).values_list('status', flat=True).first()
    else:
        instance._old_status = None

@receiver(post_save, sender=Appointment)
def appointment_notification_dispatcher(sender, instance, created, **kwargs):
    """
    Dispatches notifications based on creation or status transitions.
    """
    # 1. Determine the specific event type based on status change
    old_status = getattr(instance, '_old_status', None)
    
    if created:
        event_type = "appointment_created"
    elif old_status != instance.status:
        # Map statuses to specific event types for the notification engine
        status_map = {
            Appointment.STATUS_CONFIRMED: "appointment_confirmed",
            Appointment.STATUS_CANCELLED: "appointment_cancelled",
            Appointment.STATUS_COMPLETED: "appointment_completed",
        }
        event_type = status_map.get(instance.status, "appointment_updated")
    else:
        # No status change, skip notifications to avoid spam
        return

    # 2. Build the payload
    # Note: Use instance.appointment_id (your public ID) rather than instance.id (internal PK)
    payload = {
        "appointment_id": instance.appointment_id,
        "status": instance.status,
        "patient_name": instance.patient.get_full_name() if instance.patient else "Valued Patient",
        "vendor_name": instance.vendor.name,
        "date": instance.slot.date.strftime('%Y-%m-%d') if instance.slot else None,
        "time": str(instance.slot.start_time) if instance.slot else None,
    }

    # 3. Dispatch using on_commit to ensure notifications only send if the DB transaction succeeds
    transaction.on_commit(lambda: _dispatch_appointment_events(instance, event_type, payload))

def _dispatch_appointment_events(instance, event_type, payload):
    """Helper to handle the actual dispatching logic."""
    try:
        # Notify the Patient
        # Use patient.contact_email if booked_by_user isn't available (for guest bookings)
        recipient_user_id = instance.booked_by_user.id if instance.booked_by_user else None
        
        patient_event = DomainEvent(
            event_type=event_type,
            payload={**payload, "user_id": recipient_user_id}
        )
        dispatch_event(patient_event)

        # Notify the Lab Staff (Vendor Owner)
        vendor_owner = getattr(instance.vendor, 'owner', None)
        if vendor_owner:
            staff_event = DomainEvent(
                event_type=f"staff_{event_type}",
                payload={**payload, "user_id": vendor_owner.id}
            )
            dispatch_event(staff_event)
            
    except Exception as e:
        logger.error(f"Failed to dispatch appointment events for {instance.appointment_id}: {e}")
        