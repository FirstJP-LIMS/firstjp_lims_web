# appointment/views/slot_managements.py
# Manages lab appointment set up -- operations 
import logging
from datetime import timedelta

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import models, transaction
from django.core.paginator import Paginator
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.core.exceptions import ValidationError


from ..models import AppointmentSlot, AppointmentSlotTemplate, Appointment
from ..forms import (
    AppointmentSlotTemplateForm,
    GenerateSlotsForm,
    AppointmentSlotEditForm,
    BulkSlotActionForm
)
from apps.accounts.decorators import require_capability
# Import notification handlers
# from apps.notification.appointment_notifications import AppointmentNotifications


logger = logging.getLogger(__name__)


# =========================
# SLOT TEMPLATE MANAGEMENT
# =========================

@login_required
@require_capability('can_manage_appointment')
def slot_template_list(request):
    """
    List all appointment slot templates.
    """
    vendor = getattr(request.user, 'vendor', None) or getattr(request, 'tenant', None)
    if not vendor:
        messages.error(request, "Vendor not found.")
        return redirect('dashboard')
    
    templates = AppointmentSlotTemplate.objects.filter(
        vendor=vendor
    # ).annotate(
    #     generated_slots_count=Count('vendor__appointment_slots')
    ).order_by('-created_at')
    
    context = {
        'templates': templates,
        'vendor': vendor,
    }
    return render(request, 'laboratory/appointments/staff/slot_template_list.html', context)


@login_required
@require_capability('can_manage_appointment')
def slot_template_create(request):
    """
    Create a new appointment slot template.
    """
    vendor = getattr(request.user, 'vendor', None) or getattr(request, 'tenant', None)
    if not vendor:
        messages.error(request, "Vendor not found.")
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = AppointmentSlotTemplateForm(request.POST)
        
        if form.is_valid():
            try:
                template = form.save(commit=False)
                template.vendor = vendor
                template.created_by = request.user
                template.save()
                
                messages.success(
                    request,
                    f"✓ Slot template '{template.name}' created successfully! "
                    "Now generate actual slots from this template."
                )
                
                return redirect('appointment:slot_template_list')
            
            except Exception as e:
                logger.error(f"Error creating slot template: {e}", exc_info=True)
                messages.error(request, f"Error creating template: {str(e)}")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = AppointmentSlotTemplateForm()
    
    context = {
        'form': form,
        'vendor': vendor,
        'action': 'Create',
    }

    return render(request, 'laboratory/appointments/staff/slot_template_form.html', context)


@login_required
@require_capability('can_manage_appointment')
def slot_template_edit(request, template_id):
    """
    Edit an appointment slot template.
    """
    vendor = getattr(request.user, 'vendor', None) or getattr(request, 'tenant', None)
    if not vendor:
        messages.error(request, "Vendor not found.")
        return redirect('dashboard')
    
    template = get_object_or_404(
        AppointmentSlotTemplate,
        id=template_id,
        vendor=vendor
    )
    
    if request.method == 'POST':
        form = AppointmentSlotTemplateForm(request.POST, instance=template)
        
        if form.is_valid():
            try:
                template = form.save()
                
                messages.success(
                    request,
                    f"✓ Slot template '{template.name}' updated successfully!"
                )
                
                return redirect('appointment:slot_template_list')
            
            except Exception as e:
                logger.error(f"Error updating slot template: {e}", exc_info=True)
                messages.error(request, f"Error updating template: {str(e)}")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = AppointmentSlotTemplateForm(instance=template)
    
    context = {
        'form': form,
        'template': template,
        'vendor': vendor,
        'action': 'Edit',
    }

    return render(request, 'laboratory/appointments/staff/slot_template_form.html', context)


@login_required
@require_capability('can_manage_appointment')
@require_http_methods(["POST"])
def slot_template_delete(request, template_id):
    """
    Delete a slot template.
    """
    vendor = getattr(request.user, 'vendor', None) or getattr(request, 'tenant', None)
    if not vendor:
        messages.error(request, "Vendor not found.")
        return redirect('dashboard')
    
    template = get_object_or_404(
        AppointmentSlotTemplate,
        id=template_id,
        vendor=vendor
    )
    
    template_name = template.name
    template.delete()
    
    messages.success(request, f"Template '{template_name}' deleted successfully.")
    return redirect('appointment:slot_template_list')


# =========================================
# SLOT GENERATION
# =========================================

@login_required
@require_capability('can_manage_appointment')
def generate_slots(request):
    """
    Generate appointment slots from templates.
    """
    vendor = getattr(request.user, 'vendor', None) or getattr(request, 'tenant', None)
    if not vendor:
        messages.error(request, "Vendor not found.")
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = GenerateSlotsForm(request.POST, vendor=vendor)
        
        if form.is_valid():
            try:
                template = form.cleaned_data['template']
                start_date = form.cleaned_data['start_date']
                end_date = form.cleaned_data['end_date']
                
                # Generate slots
                slots_created = template.generate_slots(start_date, end_date)
                
                if slots_created > 0:
                    messages.success(
                        request,
                        f"✓ Successfully generated {slots_created} appointment slot(s) "
                        f"from template '{template.name}'."
                    )
                else:
                    messages.info(
                        request,
                        "No new slots were generated. Slots may already exist for this date range."
                    )
                
                return redirect('appointment:slot_calendar_view')
            
            except Exception as e:
                logger.error(f"Error generating slots: {e}", exc_info=True)
                messages.error(request, f"Error generating slots: {str(e)}")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = GenerateSlotsForm(vendor=vendor)
    
    # Get available templates
    templates = AppointmentSlotTemplate.objects.filter(
        vendor=vendor,
        is_active=True
    )
    
    context = {
        'form': form,
        'templates': templates,
        'vendor': vendor,
    }
    
    return render(request, 'laboratory/appointments/staff/generate_slots.html', context)


# =================================
# SLOT CALENDAR & MANAGEMENT
# =================================

@login_required
@require_capability('can_view_appointment')
def slot_calendar(request):
    """
    Calendar view of appointment slots with bookings.
    """
    vendor = getattr(request.user, 'vendor', None) or getattr(request, 'tenant', None)
    if not vendor:
        messages.error(request, "Vendor not found.")
        return redirect('dashboard')
    
    # Date range filter
    import pytz

    # ... inside slot_calendar ...
    vendor_tz = pytz.timezone(vendor.timezone) # Using the new field we added
    vendor_now = timezone.now().astimezone(vendor_tz)
    vendor_today = vendor_now.date()

    # Date range filter
    selected_date = request.GET.get('date')
    if selected_date:
        try:
            selected_date = timezone.datetime.strptime(selected_date, '%Y-%m-%d').date()
        except ValueError:
            selected_date = vendor_today
    else:
        selected_date = vendor_today

    # Get week range
    week_start = selected_date - timedelta(days=selected_date.weekday())
    week_end = week_start + timedelta(days=6)
    
    # Get slots for the week
    slots = AppointmentSlot.objects.filter(
        vendor=vendor,
        date__gte=week_start,
        date__lte=week_end
    ).annotate(
        available_capacity=models.F('max_appointments') - models.F('current_bookings')
    ).select_related('vendor').order_by('date', 'start_time')
    
    # Get appointments for the week
    appointments = Appointment.objects.filter(
        vendor=vendor,
        slot__date__gte=week_start,
        slot__date__lte=week_end,
        status__in=['pending', 'confirmed']
    ).select_related('slot', 'patient').order_by('slot__date', 'slot__start_time')
    
    # Group by date
    slots_by_date = {}
    for slot in slots:
        if slot.date not in slots_by_date:
            slots_by_date[slot.date] = []
        slots_by_date[slot.date].append(slot)
    
    appointments_by_date = {}
    for appointment in appointments:
        date = appointment.slot.date
        if date not in appointments_by_date:
            appointments_by_date[date] = []
        appointments_by_date[date].append(appointment)
    
    # Generate week days
    week_days = []
    current = week_start
    while current <= week_end:
        week_days.append({
            'date': current,
            'slots': slots_by_date.get(current, []),
            'appointments': appointments_by_date.get(current, []),
            'is_today': current == timezone.now().date(),
        })
        current += timedelta(days=1)
    
    # Statistics
    total_slots = slots.count()
    booked_slots = slots.filter(current_bookings__gte=models.F('max_appointments')).count()
    available_slots = total_slots - booked_slots

    import datetime
    hours = []
    for hour in range(0, 24):
        hours.append(datetime.time(hour, 0))
    
    context = {
        'week_days': week_days,
        'selected_date': selected_date,
        'week_start': week_start,
        'week_end': week_end,
        'prev_week': week_start - timedelta(days=7),
        'next_week': week_start + timedelta(days=7),
        'total_slots': total_slots,
        'booked_slots': booked_slots,
        'available_slots': available_slots,
        'vendor': vendor,
        'hours': hours,
    }
    
    return render(request, 'laboratory/appointments/staff/slot_calendar.html', context)


@login_required
@require_capability('can_view_appointment')
def slot_list(request):
    """
    List view of appointment slots with filters.
    """
    vendor = getattr(request.user, 'vendor', None) or getattr(request, 'tenant', None)
    if not vendor:
        messages.error(request, "Vendor not found.")
        return redirect('labs:vendor_dashboard')
    
    # Base queryset
    slots = AppointmentSlot.objects.filter(vendor=vendor).annotate(
        available_capacity=models.F('max_appointments') - models.F('current_bookings')
    ).select_related('vendor').order_by('date', 'start_time')
    
    # Filters
    date_filter = request.GET.get('date')
    status_filter = request.GET.get('status')
    slot_type_filter = request.GET.get('slot_type')
    
    if date_filter:
        try:
            filter_date = timezone.datetime.strptime(date_filter, '%Y-%m-%d').date()
            slots = slots.filter(date=filter_date)
        except ValueError:
            pass
    
    if status_filter == 'available':
        slots = slots.filter(
            is_active=True,
            current_bookings__lt=models.F('max_appointments'),
            date__gte=timezone.now().date()
        )
    elif status_filter == 'full':
        slots = slots.filter(current_bookings__gte=models.F('max_appointments'))
    elif status_filter == 'inactive':
        slots = slots.filter(is_active=False)
    elif status_filter == 'past':
        slots = slots.filter(date__lt=timezone.now().date())
    
    if slot_type_filter:
        slots = slots.filter(slot_type=slot_type_filter)
    
    # Pagination
    paginator = Paginator(slots, 25)
    page = request.GET.get('page', 1)
    slots = paginator.get_page(page)
    
    # Bulk action form
    bulk_form = BulkSlotActionForm()
    
    context = {
        'slots': slots,
        'date_filter': date_filter,
        'status_filter': status_filter,
        'slot_type_filter': slot_type_filter,
        'bulk_form': bulk_form,
        'vendor': vendor,
    }
    
    return render(request, 'laboratory/appointments/staff/slot_list.html', context)


@login_required
@require_capability('can_manage_appointment')
def slot_edit(request, slot_id):
    """
    Edit an individual appointment slot.
    """
    vendor = getattr(request.user, 'vendor', None) or getattr(request, 'tenant', None)
    if not vendor:
        messages.error(request, "Vendor not found.")
        return redirect('dashboard')
    
    slot = get_object_or_404(
        AppointmentSlot,
        id=slot_id,
        vendor=vendor
    )
    
    if request.method == 'POST':
        form = AppointmentSlotEditForm(request.POST, instance=slot)
        
        if form.is_valid():
            try:
                slot = form.save()
                
                messages.success(request, "Slot updated successfully!")
                return redirect('appointment:slot_calendar_view')
            
            except Exception as e:
                logger.error(f"Error updating slot: {e}", exc_info=True)
                messages.error(request, f"Error updating slot: {str(e)}")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = AppointmentSlotEditForm(instance=slot)
    
    # Get appointments for this slot
    appointments = Appointment.objects.filter(
        slot=slot,
        status__in=['pending', 'confirmed']
    ).select_related('patient')
    
    context = {
        'form': form,
        'slot': slot,
        'appointments': appointments,
        'vendor': vendor,
    }
    
    return render(request, 'laboratory/appointments/staff/slot_edit.html', context)


@login_required
@require_capability('can_manage_appointment')
def slot_delete(request, slot_id):
    """
    Delete an appointment slot if it has no bookings.
    """
    vendor = getattr(request.user, 'vendor', None) or getattr(request, 'tenant', None)
    if not vendor:
        messages.error(request, "Vendor not found.")
        return redirect('dashboard')
    
    slot = get_object_or_404(
        AppointmentSlot,
        id=slot_id,
        vendor=vendor
    )
    
    if slot.current_bookings > 0:
        messages.error(request, "Cannot delete slot with existing bookings.")
        return redirect('appointment:slot_instance_list')
    
    slot.delete()
    messages.success(request, "Slot deleted successfully.")
    return redirect('appointment:slot_instance_list')


@login_required
@require_capability('can_manage_appointment')
@require_http_methods(["POST"])
def slot_bulk_action(request):
    """
    Perform bulk actions on appointment slots.
    """
    vendor = getattr(request.user, 'vendor', None) or getattr(request, 'tenant', None)
    if not vendor:
        messages.error(request, "Vendor not found.")
        return redirect('dashboard')
    
    form = BulkSlotActionForm(request.POST)
    
    if form.is_valid():
        action = form.cleaned_data['action']
        slot_ids = form.cleaned_data['slot_ids']
        
        # Get slots
        slots = AppointmentSlot.objects.filter(
            id__in=slot_ids,
            vendor=vendor
        )
        
        if not slots.exists():
            messages.error(request, "No valid slots selected.")
            return redirect('appointment:slot_template_list')
        
        try:
            if action == 'activate':
                count = slots.update(is_active=True)
                messages.success(request, f"✓ Activated {count} slot(s).")
            
            elif action == 'deactivate':
                count = slots.update(is_active=False)
                messages.success(request, f"✓ Deactivated {count} slot(s).")
            
            elif action == 'delete':
                # Only delete slots with no bookings
                deletable = slots.filter(current_bookings=0)
                count = deletable.count()
                deletable.delete()
                
                non_deletable = slots.exclude(current_bookings=0).count()
                
                if count > 0:
                    messages.success(request, f"✓ Deleted {count} slot(s).")
                if non_deletable > 0:
                    messages.warning(
                        request,
                        f"Could not delete {non_deletable} slot(s) with existing bookings."
                    )
        
        except Exception as e:
            logger.error(f"Error performing bulk action: {e}", exc_info=True)
            messages.error(request, f"Error: {str(e)}")
    else:
        messages.error(request, "Invalid action.")
    
    return redirect('appointment:slot_instance_list')

# ========================= 
# APPOINTMENT CHECK 
# ========================= 

@login_required
@require_capability('can_view_appointment')
def staff_appointment_list(request):
    """
    Staff view to see all appointments.
    """
    vendor = getattr(request.user, 'vendor', None) or getattr(request, 'tenant', None)
    if not vendor:
        messages.error(request, "Vendor not found.")
        return redirect('account:login')
    
    appointments = Appointment.objects.filter(vendor=vendor).select_related(
        'patient', 'slot'
    ).only(
        'appointment_id', 'status', 'created_at',
        'patient__first_name', 'patient__last_name', 'patient__is_shadow',
        'slot__date', 'slot__start_time'
    )

    # Filters
    status_filter = request.GET.get('status')
    date_filter = request.GET.get('date')
    
    if status_filter:
        appointments = appointments.filter(status=status_filter)
    if date_filter:
        try:
            filter_date = timezone.datetime.strptime(date_filter, '%Y-%m-%d').date()
            appointments = appointments.filter(slot__date=filter_date)
        except ValueError:
            pass
    
    # Pagination
    paginator = Paginator(appointments, 20)
    page = request.GET.get('page', 1)
    appointments = paginator.get_page(page)
    
    context = {
        'appointments': appointments,
        'status_filter': status_filter,
        'date_filter': date_filter,
        'vendor': vendor,
    }
    
    return render(request, 'laboratory/appointments/staff/appointment_list.html', context)


@login_required
@require_capability('can_view_appointment')
@require_http_methods(["POST"])
def staff_appointment_confirm(request, appointment_id):
    appointment = get_object_or_404(Appointment, appointment_id=appointment_id)

    # if not appointment.confirm():
    # if not appointment.can_be_confirmed():
    if not appointment.can_confirm():
        messages.warning(request, "Appointment is already processed.")
        return redirect('appointment:staff_appointment_list')

    try:
        with transaction.atomic():
            appointment.confirm(user=request.user)

        messages.success(
            request,
            f"Appointment {appointment.appointment_id} confirmed."
        )
    except ValidationError as e:
        messages.error(request, str(e))
    except Exception as e:
        logger.error(f"Error confirming appointment: {e}", exc_info=True)
        messages.error(request, "An error occurred.")

    return redirect('appointment:staff_appointment_list')


