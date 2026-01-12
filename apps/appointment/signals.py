# apps/appointments/signals.py
import logging
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from .models import Appointment
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Appointment
from apps.notification.domain_events import DomainEvent
from apps.notification.engine import dispatch_event


logger = logging.getLogger(__name__)

@receiver(pre_save, sender=Appointment)
def capture_old_status(sender, instance, **kwargs):
    """
    Store the current status from the database before it is overwritten.
    """
    if instance.pk:
        try:
            old_obj = Appointment.objects.get(pk=instance.pk)
            instance._old_status = old_obj.status
        except Appointment.DoesNotExist:
            instance._old_status = None
    else:
        instance._old_status = None


@receiver(post_save, sender=Appointment)
def appointment_post_save(sender, instance, created, **kwargs):
    event_type = "appointment_created" if created else "appointment_updated"
    
    # Check if status actually changed for updates
    if not created and hasattr(instance, '_old_status'):
        if instance._old_status == instance.status:
            return 

    # Determine who should be notified
    # 1. The Patient (if they have a user account)
    # 2. The Lab Admin/Staff (Vendor)
    
    payload = {
        "appointment_id": instance.id,
        "status": instance.status,
        "summary": f"Appointment {instance.status}: {instance.patient.first_name}",
        "vendor_name": instance.vendor.name
    }

    # Notify the Patient (if authenticated)
    if instance.booked_by_user:
        patient_event = DomainEvent(
            event_type=event_type, 
            payload={**payload, "user_id": instance.booked_by_user.id}
        )
        dispatch_event(patient_event)

    # Notify the Lab Staff (The Vendor)
    # We need to find the user(s) associated with this Vendor
    # Assuming your Vendor model has an owner or staff relationship:
    vendor_owner = getattr(instance.vendor, 'owner', None) 
    if vendor_owner:
        staff_event = DomainEvent(
            event_type=f"staff_{event_type}", 
            payload={**payload, "user_id": vendor_owner.id, "summary": f"New booking: {instance.patient.get_full_name()}"}
        )
        dispatch_event(staff_event)














# @receiver(post_save, sender=Appointment)
# def appointment_post_save(sender, instance, created, **kwargs):
#     """
#     Emit a domain event when an Appointment is created or updated.
#     """
#     if not created and hasattr(instance, '_old_status'):
#         if instance._old_status == instance.status:
#             return # Skip notification if status didn't change
        
#     event_type = "appointment_created" if created else "appointment_updated"
    
#     # Payload should include the user ID (for preferences), appointment ID, etc.
#     payload = {
#         "user_id": instance.user.id,
#         "appointment_id": instance.id,
#         "status": instance.status,
#         "user_email": instance.user.email,
#         "user_phone": getattr(instance.user, "phone", None)  # optional
#     }

#     event = DomainEvent(event_type=event_type, payload=payload)
#     dispatch_event(event)



# from apps.notification.appointment_notifications import AppointmentNotifications
# @receiver(post_save, sender=Appointment)
# def trigger_appointment_notifications(sender, instance, created, **kwargs):
#     """
#     Automatically trigger notifications when an Appointment is created or status changes.
#     """
#     try:
#         if created:
#             # 1. New Appointment Created
#             logger.info(f"Signal: Sending booking confirmation for {instance.appointment_id}")
#             AppointmentNotifications.send_booking_confirmation(instance)
        
#         else:
#             # 2. Check for Status Changes
#             old_status = getattr(instance, '_old_status', None)
            
#             if old_status != instance.status:
#                 if instance.status == 'confirmed':
#                     logger.info(f"Signal: Sending confirmation for {instance.appointment_id}")
#                     AppointmentNotifications.send_confirmation(instance)
                
#                 elif instance.status == 'cancelled':
#                     logger.info(f"Signal: Sending cancellation for {instance.appointment_id}")
#                     AppointmentNotifications.send_cancellation(instance)
                
#                 elif instance.status == 'completed':
#                     # Optional: Add send_completion_notification if you create it
#                     pass

#     except Exception as e:
#         # We catch exceptions so that a notification error doesn't 
#         # crash the entire Appointment save process.
#         logger.error(f"Error in Appointment signal: {e}", exc_info=True)


