# appointments/services/booking.py
from django.db import transaction
from django.db.models import F
from django.core.exceptions import ValidationError
from apps.labs.models import Patient
from .models import AppointmentSlot, Appointment

def book_appointment(*, form, vendor, user=None):
    with transaction.atomic():
        slot = AppointmentSlot.objects.select_for_update().get(
            pk=form.cleaned_data['slot'].pk
        )

        if slot.current_bookings >= slot.max_appointments:
            raise ValidationError("This slot is fully booked.")

        patient = form.cleaned_data.get('existing_patient')

        if not patient:
            patient, _ = Patient.objects.get_or_create(
                vendor=vendor,
                contact_email=form.cleaned_data['visitor_email'],
                defaults={
                    'first_name': form.cleaned_data['visitor_first_name'],
                    'last_name': form.cleaned_data['visitor_last_name'],
                    'contact_phone': form.cleaned_data['visitor_phone'],
                    'date_of_birth': form.cleaned_data['visitor_date_of_birth'],
                    'gender': form.cleaned_data['visitor_gender'],
                    'is_shadow': True,
                }
            )

        appointment = form.save(commit=False)
        appointment.vendor = vendor
        appointment.patient = patient
        appointment.slot = slot
        if user and user.is_authenticated:
            appointment.booked_by_user = user

        appointment.save()

        AppointmentSlot.objects.filter(pk=slot.pk).update(
            current_bookings=F('current_bookings') + 1
        )

        return appointment

