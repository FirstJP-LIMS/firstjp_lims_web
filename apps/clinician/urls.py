from django.urls import path
from . import views

app_name = 'clinician'

urlpatterns = [
    path('dashboard/', views.clinician_dashboard, name='clinician_dashboard'),
    path('patients/search/', views.patient_search, name='patient_search'),
    path('patients/my-patients/', views.my_patients_list, name='my_patients'),
    path('patients/<str:patient_id>/', views.patient_detail, name='patient_detail'),
    path('patients/<str:patient_id>/history/', views.patient_test_history, name='patient_test_history'),
]


