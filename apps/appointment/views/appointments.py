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

@transaction.atomic
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
            # Domain logic handles the heavy lifting
            appointment = book_appointment(
                form=form,
                vendor=vendor,
                user=request.user
            )
            messages.success(request, "Appointment booked successfully.")
            # return redirect('appointment:public_appointment_detail', appointment_id=appointment.appointment_id)
            return redirect('appointment:public_appointment_detail', pk=appointment.id)
        except ValidationError as e:
            messages.error(request, str(e))
        except Exception as e:
            logger.error(f"Booking error: {e}")
            messages.error(request, "A system error occurred. Please try again.")

    context = {
        'form': form,
        'vendor': vendor,
        'slots_by_date': AppointmentSlot.group_by_date(
            form.fields['slot'].queryset
        )
    }

    return render(
        request,
        'laboratory/appointments/patient/booking_form1.html',
        # 'laboratory/appointments/patient/bookingform.html',
        context
    )


def appointment_detail(request, pk):
    vendor = getattr(request, 'tenant', None)
    if not vendor:
        raise Http404("Laboratory context not found.")

    appointment = get_object_or_404(
        Appointment.objects.select_related(
            'patient', 
            'slot', 
            'test_request', 
            'booked_by_user'
        ),
        pk=pk,
        vendor=vendor
    )

    context = {
        'appointment': appointment,
        'vendor': vendor,
        'is_visitor': not request.user.is_authenticated,
    }
    
    return render(request, 'laboratory/appointments/patient/appt_detail.html', context)


# def appointment_detail(request, appointment_id):
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
    
#     context = {
#     'appointment': appointment,
#     'can_cancel': appointment.can_cancel(),  # ✅ Returns True/False
#     'can_confirm': appointment.can_confirm(),  # Bonus!
#     'is_active': appointment.is_active,  # Bonus!
#     }
    
#     return render(request, 'laboratory/appointments/patient/appointment_confirmation.html', context)




# def appointment_detail(request, appointment_id):
#     """
#     Public-facing detail page. Displays current status of the appointment.
#     """
#     appointment = get_object_or_404(Appointment, appointment_id=appointment_id)
    
#     # SECURITY: Ensure only authorized people can see this
#     # We allow: 1. The owner, 2. The staff, or 3. The person who just booked it (session-based)
#     is_owner = request.user.is_authenticated and (
#         appointment.booked_by_user == request.user or 
#         getattr(request.user, 'vendor_id', None) == appointment.vendor_id
#     )

#     # In a production LIMS, you might allow guest access via the unique appointment_id string,
#     # but strictly limit what personal info is shown if not logged in.
    
#     context = {
#         'appointment': appointment,
#         'can_cancel': appointment.can_cancel(),
#         'can_confirm': appointment.can_confirm(),
#         'is_active': appointment.is_active,
#     }
    
#     return render(request, 'laboratory/appointments/patient/appointment_detail.html', context)


# @require_http_methods(["POST"])
# def appointment_confirm(request, appointment_id):
#     appointment = get_object_or_404(Appointment, appointment_id=appointment_id)

#     try:
#         # The model method already checks 'can_confirm' via 'transition'
#         appointment.confirm(user=request.user if request.user.is_authenticated else None)
#         messages.success(request, "Appointment confirmed successfully.")
#     except ValidationError as e:
#         messages.error(request, str(e))

#     return redirect('appointment:public_appointment_detail', appointment_id=appointment_id)


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
    
#     # ❌ WRONG: if not appointment.cancel:
#     # ✅ CORRECT:
#     if not appointment.can_cancel():
#         messages.error(request, "This appointment cannot be cancelled.")
#         return redirect('appointment:public_appointment_detail', appointment_id=appointment_id)
    
#     reason = request.POST.get('cancellation_reason', 'Cancelled by patient')
    
#     try:
#         with transaction.atomic():
#             appointment.cancel(
#                 reason=reason, 
#                 cancelled_by_user=request.user if request.user.is_authenticated else None
#             )
            
#             messages.success(request, "Appointment cancelled successfully.")
#     except Exception as e:
#         logger.error(f"Error cancelling appointment: {e}", exc_info=True)
#         messages.error(request, "An error occurred while cancelling the appointment.")
    
#     return redirect('appointment:public_appointment_detail', appointment_id=appointment_id)




# @require_http_methods(["POST"])
# def appointment_confirm(request, appointment_id):
#     appointment = get_object_or_404(Appointment, appointment_id=appointment_id)

#     if not appointment.can_confirm():
#         messages.error(request, "This appointment cannot be confirmed.")
#         return redirect(
#             'appointment:public_appointment_detail',
#             appointment_id=appointment_id
#         )

#     try:
#         appointment.confirm(
#             user=request.user if request.user.is_authenticated else None
#         )
#         messages.success(request, "Appointment confirmed successfully.")
#     except ValidationError as e:
#         messages.error(request, str(e))

#     return redirect(
#         'appointment:public_appointment_detail',
#         appointment_id=appointment_id
#     )
