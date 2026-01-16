# appointment/views/appointments.py
"""
    It manages walk-in patient, unathenticated appointment booking 
"""
import logging
from django.http import Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from django.db import transaction
from django.core.paginator import Paginator
from django.views.decorators.http import require_http_methods
from django.core.exceptions import ValidationError
from ..models import Appointment, AppointmentSlot
from ..forms import AppointmentBookingForm
from ..services import book_appointment
from apps.labs.models import Patient
from apps.tenants.models import Vendor
# from apps.notification.appointment_notifications import AppointmentNotifications


logger = logging.getLogger(__name__)

from django.http import Http404

def appointment_booking(request):
    vendor = getattr(request, 'tenant', None)

    if not vendor:
        raise Http404("Vendor context not resolved")

    form = AppointmentBookingForm(
        request.POST or None,
        vendor=vendor,
        user=request.user if request.user.is_authenticated else None
    )

    if request.method == 'POST' and form.is_valid():
        try:
            appointment = book_appointment(
                form=form,
                vendor=vendor,
                user=request.user
            )
            messages.success(request, "Appointment booked successfully.")
            return redirect(
                'appointment:public_appointment_detail',
                appointment_id=appointment.appointment_id
            )
        except ValidationError as e:
            messages.error(request, str(e))

    context = {
        'form': form,
        'vendor': vendor,
        'slots_by_date': AppointmentSlot.group_by_date(
            form.fields['slot'].queryset
        )
    }

    return render(
        request,
        'laboratory/appointments/patient/booking_form.html',
        context
    )


def appointment_confirmation(request, appointment_id):
    """
    Appointment confirmation page - shows booking details.
    """
    appointment = get_object_or_404(Appointment, appointment_id=appointment_id)
    
    # Allow access if:
    # 1. User booked it (authenticated)
    # 2. Visitor can access via appointment_id (public link)
    can_view = (
        (request.user.is_authenticated and appointment.booked_by_user == request.user) or
        (appointment.patient and request.user.is_authenticated and 
         hasattr(request.user, 'patient_profile') and 
         request.user.patient_profile.patient == appointment.patient)
    )
    
    # For now, allow public access via appointment_id (you can add security token later)
    
    context = {
        'appointment': appointment,
        'can_cancel': appointment.can_be_cancelled,
    }
    
    return render(request, 'laboratory/appointments/patient/appointment_confirmation.html', context)


@require_http_methods(["POST"])
def appointment_cancel(request, appointment_id):
    """
    Cancel an appointment.
    """
    appointment = get_object_or_404(Appointment, appointment_id=appointment_id)
    
    # Check permissions
    can_cancel = (
        (request.user.is_authenticated and appointment.booked_by_user == request.user) or
        (appointment.patient and request.user.is_authenticated and 
         hasattr(request.user, 'patient_profile') and 
         request.user.patient_profile.patient == appointment.patient)
    )
    
    if not can_cancel:
        messages.error(request, "You don't have permission to cancel this appointment.")
        return redirect('appointment:public_appointment_detail', appointment_id=appointment_id)
    
    if not appointment.can_be_cancelled:
        messages.error(request, "This appointment cannot be cancelled.")
        return redirect('appointment:public_appointment_detail', appointment_id=appointment_id)
    
    reason = request.POST.get('cancellation_reason', 'Cancelled by patient')
    
    try:
        with transaction.atomic():
            appointment.cancel(
                reason=reason, 
                cancelled_by_user=request.user if request.user.is_authenticated else None
            )
            
            # ============================================
            # SEND CANCELLATION NOTIFICATIONS
            # ============================================
            # try:
            #     # TODO: 
            #     pass

            # except Exception as e:
            #     logger.error(f"Failed to send cancellation notification: {e}", exc_info=True)
            #     # Don't fail the cancellation if notification fails
            
            messages.success(request, "Appointment cancelled successfully.")
    except Exception as e:
        logger.error(f"Error cancelling appointment: {e}", exc_info=True)
        messages.error(request, "An error occurred while cancelling the appointment.")
    
    return redirect('appointment:public_appointment_detail', appointment_id=appointment_id)


















# # appointment/views/appointments.py
# import logging
# from django.shortcuts import render, redirect, get_object_or_404
# from django.contrib import messages
# from django.utils import timezone
# from django.db import transaction
# from django.core.paginator import Paginator
# from django.views.decorators.http import require_http_methods
# from django.core.exceptions import ValidationError
# from ..models import Appointment, AppointmentSlot
# from ..forms import AppointmentBookingForm
# from apps.labs.models import Patient, Vendor
# from apps.notification.appointment_notifications import AppointmentNotifications


# logger = logging.getLogger(__name__)


# def appointment_booking(request, vendor_slug=None):
#     """
#     Public appointment booking page - accessible to both authenticated and unauthenticated users.
#     """
#     # Get vendor (from slug, session, or user)
#     vendor = None
#     if vendor_slug:
#         vendor = get_object_or_404(Vendor, slug=vendor_slug, is_active=True)
#     elif hasattr(request, 'tenant'):
#         vendor = request.tenant
#     elif request.user.is_authenticated and hasattr(request.user, 'vendor'):
#         vendor = request.user.vendor
    
#     if not vendor:
#         messages.error(request, "Laboratory not found.")
#         return redirect('home')
    
#     if request.method == 'POST':
#         form = AppointmentBookingForm(
#             request.POST,
#             vendor=vendor,
#             user=request.user if request.user.is_authenticated else None
#         )
        
#         if form.is_valid():
#             try:
#             # The transaction.atomic() is now inside form.save() 
#                 appointment = form.save()
                
#                 # TRIGGER NOTIFICATIONS (We will refine these next)
#                 # TODO: 
#                 pass
#                 # AppointmentNotifications.send_booking_confirmation(appointment)
                
#                 messages.success(request, f"✓ Appointment {appointment.appointment_id} booked!")
#                 return redirect('appointment:public_appointment_detail', appointment_id=appointment.appointment_id)
            
#             except ValidationError as e:
#                 messages.error(request, str(e))
#             except Exception as e:
#                 logger.error(f"Booking error: {e}", exc_info=True)
#                 messages.error(request, "A system error occurred.")
                
#         else:
#             messages.error(request, "Please correct the errors below.")
#     else:
#         form = AppointmentBookingForm(
#             vendor=vendor,
#             user=request.user if request.user.is_authenticated else None
#         )
    
#     # Group slots by date for better UX
#     available_slots = form.fields['slot'].queryset
#     slots_by_date = {}
#     for slot in available_slots:
#         if slot.date not in slots_by_date:
#             slots_by_date[slot.date] = []
#         slots_by_date[slot.date].append(slot)
    
#     context = {
#         'form': form,
#         'vendor': vendor,
#         'slots_by_date': slots_by_date,
#         'is_authenticated': request.user.is_authenticated,
#     }
    
#     return render(request, 'laboratory/appointments/patient/booking_form.html', context)


# def appointment_confirmation(request, appointment_id):
#     """
#     Appointment confirmation page - shows booking details.
#     """
#     appointment = get_object_or_404(Appointment, appointment_id=appointment_id)
    
#     # Allow access if:
#     # 1. User booked it (authenticated)
#     # 2. Visitor can access via appointment_id (public link)
#     can_view = (
#         (request.user.is_authenticated and appointment.booked_by_user == request.user) or
#         (appointment.patient and request.user.is_authenticated and 
#          hasattr(request.user, 'patient_profile') and 
#          request.user.patient_profile.patient == appointment.patient)
#     )
    
#     # For now, allow public access via appointment_id (you can add security token later)
    
#     context = {
#         'appointment': appointment,
#         'can_cancel': appointment.can_be_cancelled,
#     }
    
#     return render(request, 'laboratory/appointments/patient/appointment_confirmation.html', context)


# @require_http_methods(["POST"])
# def appointment_cancel(request, appointment_id):
#     """
#     Cancel an appointment.
#     """
#     appointment = get_object_or_404(Appointment, appointment_id=appointment_id)
    
#     # Check permissions
#     can_cancel = (
#         (request.user.is_authenticated and appointment.booked_by_user == request.user) or
#         (appointment.patient and request.user.is_authenticated and 
#          hasattr(request.user, 'patient_profile') and 
#          request.user.patient_profile.patient == appointment.patient)
#     )
    
#     if not can_cancel:
#         messages.error(request, "You don't have permission to cancel this appointment.")
#         return redirect('appointment:public_appointment_detail', appointment_id=appointment_id)
    
#     if not appointment.can_be_cancelled:
#         messages.error(request, "This appointment cannot be cancelled.")
#         return redirect('appointment:public_appointment_detail', appointment_id=appointment_id)
    
#     reason = request.POST.get('cancellation_reason', 'Cancelled by patient')
    
#     try:
#         with transaction.atomic():
#             appointment.cancel(
#                 reason=reason, 
#                 cancelled_by_user=request.user if request.user.is_authenticated else None
#             )
            
#             # ============================================
#             # SEND CANCELLATION NOTIFICATIONS
#             # ============================================
#             try:
#                 # TODO: 
#                 pass
#                 # AppointmentNotifications.send_cancellation(appointment)
#                 # logger.info(f"Cancellation notification sent for {appointment.appointment_id}")
#             except Exception as e:
#                 logger.error(f"Failed to send cancellation notification: {e}", exc_info=True)
#                 # Don't fail the cancellation if notification fails
            
#             messages.success(request, "Appointment cancelled successfully.")
#     except Exception as e:
#         logger.error(f"Error cancelling appointment: {e}", exc_info=True)
#         messages.error(request, "An error occurred while cancelling the appointment.")
    
#     return redirect('appointment:public_appointment_detail', appointment_id=appointment_id)

# appointment/views/appointments.py
