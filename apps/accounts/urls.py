from django.urls import path
from . import views

app_name = "account"

urlpatterns = [
    # path('register/', views.tenant_register_by_role, name='register'),
    # 3. REGISTRATION ROUTES (All point to the same view, passing the role)
    path('register/staff/', views.tenant_register_by_role, {'role_name': 'lab_staff'}, name='staff_register'),

    path('register/clinician/', views.tenant_register_by_role, {'role_name': 'clinician'}, name='clinician_register'),
    
    path('register/patient/', views.tenant_register_by_role, {'role_name': 'patient'}, name='patient_register'),

    path('login/', views.tenant_login, name='login'),
    
    path('logout/', views.tenant_logout, name='logout'),
]

