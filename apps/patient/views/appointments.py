# patients/views/appointments.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from django.db import transaction
from django.core.paginator import Paginator
from django.views.decorators.http import require_http_methods

from ..models import Appointment, AppointmentSlot
from ..forms import AppointmentBookingForm
from apps.labs.models import Patient, Vendor

import logging
logger = logging.getLogger(__name__)


def appointment_booking(request, vendor_slug=None):
    """
    Public appointment booking page - accessible to both authenticated and unauthenticated users.
    """
    # Get vendor (from slug, session, or user)
    vendor = None
    if vendor_slug:
        vendor = get_object_or_404(Vendor, slug=vendor_slug, is_active=True)
    elif hasattr(request, 'tenant'):
        vendor = request.tenant
    elif request.user.is_authenticated and hasattr(request.user, 'vendor'):
        vendor = request.user.vendor
    
    if not vendor:
        messages.error(request, "Laboratory not found.")
        return redirect('home')
    
    if request.method == 'POST':
        form = AppointmentBookingForm(
            request.POST,
            vendor=vendor,
            user=request.user if request.user.is_authenticated else None
        )
        
        if form.is_valid():
            try:
                with transaction.atomic():
                    appointment = form.save()
                    
                    # TODO: Send confirmation email/SMS
                    # send_appointment_confirmation(appointment)
                    
                    messages.success(
                        request,
                        f"✓ Appointment {appointment.appointment_id} booked successfully! "
                        f"You'll receive a confirmation at {appointment.get_contact_email() or appointment.get_contact_phone()}."
                    )
                    
                    return redirect('patients:appointment_confirmation', appointment_id=appointment.appointment_id)
            
            except Exception as e:
                logger.error(f"Error booking appointment: {e}", exc_info=True)
                messages.error(request, f"An error occurred: {str(e)}")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = AppointmentBookingForm(
            vendor=vendor,
            user=request.user if request.user.is_authenticated else None
        )
    
    # Group slots by date for better UX
    available_slots = form.fields['slot'].queryset
    slots_by_date = {}
    for slot in available_slots:
        if slot.date not in slots_by_date:
            slots_by_date[slot.date] = []
        slots_by_date[slot.date].append(slot)
    
    context = {
        'form': form,
        'vendor': vendor,
        'slots_by_date': slots_by_date,
        'is_authenticated': request.user.is_authenticated,
    }
    
    return render(request, 'patient/appointments/booking_form.html', context)


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
    
    return render(request, 'patient/appointments/confirmation.html', context)


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
        return redirect('patients:appointment_confirmation', appointment_id=appointment_id)
    
    if not appointment.can_be_cancelled:
        messages.error(request, "This appointment cannot be cancelled.")
        return redirect('patients:appointment_confirmation', appointment_id=appointment_id)
    
    reason = request.POST.get('cancellation_reason', 'Cancelled by patient')
    
    try:
        appointment.cancel(reason=reason, cancelled_by_user=request.user if request.user.is_authenticated else None)
        
        # TODO: Send cancellation notification
        # send_appointment_cancellation(appointment)
        
        messages.success(request, "Appointment cancelled successfully.")
    except Exception as e:
        logger.error(f"Error cancelling appointment: {e}", exc_info=True)
        messages.error(request, "An error occurred while cancelling the appointment.")
    
    return redirect('patients:appointment_confirmation', appointment_id=appointment_id)


# === STAFF VIEWS (for managing appointments) ===

from django.contrib.auth.decorators import login_required

@login_required
def staff_appointment_list(request):
    """
    Staff view to see all appointments.
    """
    vendor = getattr(request.user, 'vendor', None) or getattr(request, 'tenant', None)
    if not vendor:
        messages.error(request, "Vendor not found.")
        return redirect('dashboard')
    
    appointments = Appointment.objects.filter(vendor=vendor).select_related(
        'patient', 'slot', 'booked_by_user'
    ).order_by('-created_at')
    
    # Filters
    status_filter = request.GET.get('status')
    date_filter = request.GET.get('date')
    
    if status_filter:
        appointments = appointments.filter(status=status_filter)
    if date_filter:
        appointments = appointments.filter(slot__date=date_filter)
    
    # Pagination
    paginator = Paginator(appointments, 20)
    page = request.GET.get('page', 1)
    appointments = paginator.get_page(page)
    
    context = {
        'appointments': appointments,
        'status_filter': status_filter,
        'date_filter': date_filter,
    }
    
    return render(request, 'staff/appointments/list.html', context)


@login_required
@require_http_methods(["POST"])
def staff_appointment_confirm(request, appointment_id):
    """
    Staff confirms an appointment.
    """
    appointment = get_object_or_404(Appointment, appointment_id=appointment_id)
    
    if appointment.status != 'pending':
        messages.warning(request, "Appointment is already processed.")
        return redirect('patients:staff_appointment_list')
    
    try:
        appointment.confirm(confirmed_by_user=request.user)
        
        # TODO: Send confirmation to patient
        
        messages.success(request, f"Appointment {appointment_id} confirmed.")
    except Exception as e:
        logger.error(f"Error confirming appointment: {e}", exc_info=True)
        messages.error(request, "An error occurred.")
    
    return redirect('patients:staff_appointment_list')
