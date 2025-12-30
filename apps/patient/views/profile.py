from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.db import transaction
from apps.labs.models import VendorTest, TestRequest, Department
from ..forms import PatientProfileForm, PatientTestOrderForm
from ..models import PatientUser
from django.utils import timezone


"""
accounts:
kunle@gmail.com
password#1
"""


@login_required
def patient_dashboard(request):
    """Patient portal dashboard."""
    try:
        patient_user = request.user.patient_profile
        patient = patient_user.patient
    except PatientUser.DoesNotExist:
        messages.error(request, "Patient profile not found.")
        return redirect('account:login')
    
    # Update last login
    patient_user.update_last_login()
    
    # Get recent requests
    recent_requests = patient.requests.all()[:5]
    
    # Profile completeness
    profile_complete = patient_user.is_profile_complete
    
    context = {
        'patient': patient,
        'patient_user': patient_user,
        'recent_requests': recent_requests,
        'profile_complete': profile_complete,
    }
    
    return render(request, 'patient/dashboard.html', context)

# PROFILE MGT 
@login_required
def patient_profile_view(request):
    """
    View patient profile (read-only display).
    """
    try:
        patient_user = request.user.patient_profile
        patient = patient_user.patient
    except PatientUser.DoesNotExist:
        messages.error(request, "Patient profile not found.")
        return redirect('patient:patient_dashboard')
    
    # Calculate profile completeness
    completeness = calculate_profile_completeness(patient, patient_user)
    
    context = {
        'patient': patient,
        'patient_user': patient_user,
        'user': request.user,
        'completeness': completeness,
    }
    
    return render(request, 'patient/profile/profile_detail.html', context)


@login_required
def patient_profile_edit(request):
    """
    Edit patient profile information.
    """
    try:
        patient_user = request.user.patient_profile
        patient = patient_user.patient
    except PatientUser.DoesNotExist:
        messages.error(request, "Patient profile not found.")
        return redirect('patient:patient_dashboard')
    
    if request.method == 'POST':
        form = PatientProfileForm(
            request.POST,
            patient=patient,
            patient_user=patient_user
        )
        
        if form.is_valid():
            try:
                patient, patient_user = form.save()
                messages.success(request, "Profile updated successfully!")
                return redirect('patients:profile_view')
            except Exception as e:
                messages.error(request, f"Error updating profile: {str(e)}")
    else:
        form = PatientProfileForm(
            patient=patient,
            patient_user=patient_user
        )
    
    context = {
        'form': form,
        'patient': patient,
        'patient_user': patient_user,
    }
    
    return render(request, 'patient/profile/profile_update_form.html', context)


def calculate_profile_completeness(patient, patient_user):
    """
    Calculate profile completion percentage and identify missing fields.
    """
    fields = {
        'First Name': patient.first_name,
        'Last Name': patient.last_name,
        'Date of Birth': patient.date_of_birth,
        'Gender': patient.gender,
        'Phone Number': patient.contact_phone,
        'Email': patient.contact_email,
        'Digital Consent': patient_user.consent_to_digital_results,
        'Email Verified': patient_user.email_verified,
    }
    
    filled = sum(1 for value in fields.values() if value)
    total = len(fields)
    percentage = int((filled / total) * 100)
    
    missing = [key for key, value in fields.items() if not value]
    
    return {
        'percentage': percentage,
        'filled': filled,
        'total': total,
        'missing_fields': missing,
        'is_complete': percentage == 100
    }

