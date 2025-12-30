from django.urls import path
# from . import views
from .views import appointments, profile, test_request, slot_managements

app_name = "patient"

urlpatterns = [
    path("", profile.patient_dashboard, name="patient_dashboard"),

    # profile 
    path("profile/", profile.patient_profile_view, name="profile_view"),
    path("update/", profile.patient_profile_edit, name="profile_edit"),

    # Order - Request
    path('tests/', test_request.patient_test_catalog, name='test_catalog'),
    path('orders/new/', test_request.patient_create_order, name='create_order'),
    path('orders/', test_request.patient_order_list, name='orders_list'),
    path('orders/<str:request_id>/', test_request.patient_order_detail, name='order_detail'),

    # Results
    path('results/<str:request_id>/', test_request.patient_view_results, name='view_results'),
    path('results/<str:request_id>/download/', test_request.patient_download_results, name='download_results'),

    # Public appointment booking
    path('appointments/book/', appointments.appointment_booking, name='appointment_booking'),
    path('appointments/book/<slug:vendor_slug>/', appointments.appointment_booking, name='appointment_booking_vendor'),
    path('appointments/<str:appointment_id>/', appointments.appointment_confirmation, name='appointment_confirmation'),
    path('appointments/<str:appointment_id>/cancel/', appointments.appointment_cancel, name='appointment_cancel'),
    
    # Staff appointment management
    path('staff/appointments/', appointments.staff_appointment_list, name='staff_appointment_list'),
    path('staff/appointments/<str:appointment_id>/confirm/', appointments.staff_appointment_confirm, name='staff_appointment_confirm'),

    # Slot Management
    path('slot/list/', slot_managements.slot_template_list, name='slot_list'),
    path('slot/create/', slot_managements.slot_template_create, name='slot_create'),
    path('slot/<int:template_id>/edit/', slot_managements.slot_template_edit, name="slot_edit"),
    path('slot/<int:template_id>/delete/', slot_managements.slot_template_delete, name="slot_delete"),

    # slot generation
    path('slot/<int:template_id>/generate/', slot_managements.generate_slots, name="generate_slots"),

    # slot Calendar 
    path('slot/calendar/', slot_managements.slot_calendar, name="slot_calendar"),
    path('slot/calendar/list', slot_managements.slot_list, name="slot_appointment_list"),
    path('slot/calendar/<int:slot_id>/edit', slot_managements.slot_edit, name="slot_appointment_edit"),
    path('slot/calendar/delete', slot_managements.slot_bulk_action, name="slot_bulk_action"),
]

