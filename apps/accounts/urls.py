# apps/accounts/urls.py
from django.urls import path
from . import views
from django.contrib.auth import views as auth_views

app_name = "account"

urlpatterns = [
    
    path('index/', views.tenant_auth_page, name='auth_landing'),
    # REGISTRATION ROUTES
    path('register/staff/', 
         views.tenant_register_by_role, 
         {'role_name': 'lab_staff'}, 
         name='staff_register'),
    
    path('register/clinician/', 
         views.tenant_register_by_role, 
         {'role_name': 'clinician'}, 
         name='clinician_register'),
    
    path('register/patient/', 
         views.tenant_register_by_role, 
         {'role_name': 'patient'}, 
         name='patient_register'),

    # AUTHENTICATION
    path('login/', views.tenant_login, name='login'),
    path('logout/', views.tenant_logout, name='logout'),

    # PASSWORD RESET (Tenant-scoped)
    path('password-reset/', 
         views.TenantPasswordResetView,
         name='password_reset'),
    
    path('password-reset/done/', 
         auth_views.PasswordResetDoneView.as_view(
             template_name='registration/password_reset_done.html'
         ), 
         name='password_reset_done'),
    
    path('reset/<uidb64>/<token>/', 
         auth_views.PasswordResetConfirmView.as_view(
             template_name='registration/password_reset_confirm.html'
         ), 
         name='password_reset_confirm'),
    
    path('reset/done/', 
         auth_views.PasswordResetCompleteView.as_view(
             template_name='registration/password_reset_complete.html'
         ), 
         name='password_reset_complete'),

    # Laboratory profile 
    path("profile/", views.vendor_profile, name="laboratory_profile"),
    
    # Euipment Management
    path("profile/equipment/", views.equipment_list, name="equipment_list"),

    path("profile/equipment/create/", views.equipment_create, name="equipment_create"),

    path("profile/equipment/detail/<int:equipment_id>/", views.equipment_detail, name="equipment_detail"),

    path("profile/equipment/<int:equipment_id>/edit/", views.equipment_update, name="equipment_update"),

    path("profile/equipment/<int:equipment_id>/calibrate/", views.equipment_calibrate, name="equipment_calibrate"),
    
    path('profile/equipment/<int:equipment_id>/deactivate/', views.equipment_deactivate, name='equipment_deactivate'),

    path('profile/equipment/<int:equipment_id>/test-connection/', views.equipment_test_connection, name='equipment_test_connection'),
    

    # path('profile/equipment/', views.manage_equipment, name='manage_equipment'),


]

