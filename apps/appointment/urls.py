from django.urls import path
from .views import appointments, slot_managements

app_name = "appointment"

urlpatterns = [

    # =====================================================
    # PUBLIC / PATIENT-FACING APPOINTMENTS
    # =====================================================
    path('booking/confirmation/<uuid:pk>/', appointments.appointment_detail, name='public_appointment_detail'),

    path('booking/', appointments.appointment_booking,name='public_appointment_book'), # To be used by visitors without authetication
    
    path('appointments/book/<slug:subdomain_prefix>/', appointments.appointment_booking, name='public_appointment_book_vendor'), # To be used in the lab or by registered patient

    path('appointments/book/<int:vendor_id>/', appointments.appointment_booking, name='public_appointment_book_vendor'), # To be used in the lab or by registered patient

    # # Should be for staffs 
     
    # ========================================
    # STAFF — APPOINTMENT OPERATIONS
    # ========================================
    path('staff/appointments/', slot_managements.staff_appointment_list, name='staff_appointment_list'),

    path('staff/appointments/<uuid:pk>/', slot_managements.staff_appointment_detail, name='staff_appointment_detail'),
    
    path('staff/appointments/<uuid:pk>/confirm/', slot_managements.staff_appointment_status_update, name='appointment_status_update'),

    path('appointments/<str:appointment_id>/confirm/', slot_managements.staff_appointment_confirm, name='staff_appointment_confirm'), 
    
    # Added

    # =====================================================
    # SLOT TEMPLATES (HOW THE LAB WORKS)
    # =====================================================
    path('slot/templates/', slot_managements.slot_template_list, name='slot_template_list'),  # marked
    path('slot/templates/create/', slot_managements.slot_template_create, name='slot_template_create'),  # marked 
    path('slot/templates/<int:template_id>/edit/', slot_managements.slot_template_edit, name='slot_template_edit'), # marked
    path('slot/templates/<int:template_id>/delete/', slot_managements.slot_template_delete, name='slot_template_delete'), # marked
    path('slot/templates/generate/', slot_managements.generate_slots, name='slot_template_generate'), # marked 

    # =====================================================
    # SLOT INSTANCES (CALENDAR / REAL AVAILABILITY)
    # =====================================================
    path('slots/calendar/', slot_managements.slot_calendar, name='slot_calendar_view'), # marked
    path(
        'slots/calendar/list/',
        slot_managements.slot_list,
        name='slot_instance_list'
    ),
    path(
        'slots/calendar/<int:slot_id>/edit/',
        slot_managements.slot_edit,
        name='slot_instance_edit'
    ),
    path(
        'slots/calendar/<int:slot_id>/delete/',
        slot_managements.slot_delete,
        name='slot_instance_delete'
    ),
    path(
        'slots/calendar/bulk/',
        slot_managements.slot_bulk_action,
        name='slot_instance_bulk_action'
    ),
]

