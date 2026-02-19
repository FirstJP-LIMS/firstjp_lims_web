# apps/accounts/urls.py
from django.urls import path
# from . import views
from .views import equipment_setup, profile, auth, users 

from django.contrib.auth import views as auth_views

app_name = "account"

urlpatterns = [
    
     # path('index/', views.tenant_auth_page, name='auth_landing'),
    # REGISTRATION ROUTES
     # laboratory roles
    path('register/staff/', auth.tenant_register_by_role, {'role_name': 'lab_staff'}, name='staff_register'),

    path('register/clinician/', auth.tenant_register_by_role, {'role_name': 'clinician'}, name='clinician_register'),    
    
    path('register/patient/', auth.tenant_register_by_role, {'role_name': 'patient'}, name='patient_register'),

     # learning platform roles 
    path('register/learner/', auth.learn_register, {'role_name':'learner'}, name='learner_register'),
     
    path('register/facilitator/', auth.learn_register, {'role_name':'facilitator'}, name='facilitator_register'),

    # AUTHENTICATION
    path('login/', auth.tenant_login, name='login'),
    path('logout/', auth.tenant_logout, name='logout'),

    # PASSWORD RESET (Tenant-scoped)
    # Step 1: Request password reset
    path('password-reset/', 
         auth.TenantPasswordResetView.as_view(), name='password_reset'
         ),

    # path('password-reset/done/', auth_views.PasswordResetDoneView.as_view(template_name='registration/password_reset_done.html'), name='password_reset_done'),

    # path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(template_name='registration/password_reset_confirm.html'), name='password_reset_confirm'),

    # path('reset/done/', auth_views.PasswordResetCompleteView.as_view(template_name='registration/password_reset_complete.html'), name='password_reset_complete'),

    # Step 2: Email sent confirmation
    path(
        'password-reset/done/',
        auth.TenantPasswordResetDoneView.as_view(),
        name='password_reset_done'
    ),
    
    # Step 3: Set new password (from email link)
    path(
        'password-reset/confirm/<uidb64>/<token>/',
        auth.TenantPasswordResetConfirmView.as_view(),
        name='password_reset_confirm'
    ),
    
    # Step 4: Reset complete
    path(
        'password-reset/complete/',
        auth.TenantPasswordResetCompleteView.as_view(),
        name='password_reset_complete'
    ),
    
    # ==============================================
    # PASSWORD RESET (Learning Portal)
    # ==============================================
    path(
        'learn/password-reset/',
        auth.LearnPasswordResetView.as_view(),
        name='learn_password_reset'
    ),
    # Reuse done/confirm/complete views (they check is_learning_portal flag)


    # Laboratory profile 
    path("profile/", profile.vendor_profile, name="laboratory_profile"),
    
     # Role Management 
     path("staffs/", users.user_list, name="user_staff_list"),
     path("users/create/", users.user_create, name="user_create"),
     path("users/<int:user_id>/change-role/", users.user_change_role, name="user_change_role"),
     path("users/<int:user_id>/", users.user_toggle_status, name="user_toggle_status"),
     path("users/detail/<int:user_id>/", users.user_detail, name="user_detail"),
     path("users/<int:user_id>/suspend/", users.user_suspend, name="user_suspend"),
     path("users/<int:user_id>/deactivate/", users.user_deactivate, name="user_deactivate"),

     # Audit
     path("audit-logs/", users.full_audit_log, name="audit_log_list"),

    # Euipment Management
    path("profile/equipment/", equipment_setup.equipment_list, name="equipment_list"),
    path("profile/equipment/create/", equipment_setup.equipment_create, name="equipment_create"),
    path("profile/equipment/detail/<int:equipment_id>/", equipment_setup.equipment_detail, name="equipment_detail"),
    path("profile/equipment/<int:equipment_id>/edit/", equipment_setup.equipment_update, name="equipment_update"),
    path("profile/equipment/<int:equipment_id>/calibrate/", equipment_setup.equipment_calibrate, name="equipment_calibrate"),
    path('profile/equipment/<int:equipment_id>/deactivate/', equipment_setup.equipment_deactivate, name='equipment_deactivate'),
    path('profile/equipment/<int:equipment_id>/test-connection/', equipment_setup.equipment_test_connection, name='equipment_test_connection'),
    
    # path('profile/equipment/', views.manage_equipment, name='manage_equipment'),
]

