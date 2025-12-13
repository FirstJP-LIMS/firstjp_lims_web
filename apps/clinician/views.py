from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Q, Count, Max
from django.core.paginator import Paginator
from apps.labs.models import Patient, TestRequest
from .models import ClinicianProfile, ClinicianPatientRelationship


@login_required
def clinician_dashboard(request):
    """Main dashboard for clinicians."""
    if request.user.role != 'clinician':
        messages.error(request, "Access denied. Clinician account required.")
        return redirect('account:login')
    
    try:
        clinician_profile = request.user.clinician_profile
    except ClinicianProfile.DoesNotExist:
        messages.error(request, "Clinician profile not found.")
        return redirect('account:login')
    
    # Get clinician's patients (those they've ordered tests for)
    my_patients = Patient.objects.filter(
        clinician_relationships__clinician=request.user,
        clinician_relationships__is_active=True
    ).distinct()
    
    # Recent orders
    recent_orders = TestRequest.objects.filter(
        ordering_clinician=request.user
    ).select_related('patient').order_by('-created_at')[:10]
    
    # Pending results (orders completed but not acknowledged)
    pending_results = TestRequest.objects.filter(
        ordering_clinician=request.user,
        status='V',  # Verified
        clinician_acknowledged_at__isnull=True
    ).count()
    
    # Critical results needing attention
    critical_results = TestRequest.objects.filter(
        ordering_clinician=request.user,
        status='V',
        # TODO: Add logic to identify critical values
    ).count()
    
    context = {
        'clinician_profile': clinician_profile,
        'total_patients': my_patients.count(),
        'total_orders': clinician_profile.total_orders_placed,
        'pending_results': pending_results,
        'critical_results': critical_results,
        'recent_orders': recent_orders,
    }
    
    return render(request, 'clinician/dashboard.html', context)


@login_required
def patient_search(request):
    """Search for patients to view or order tests."""
    if request.user.role != 'clinician':
        messages.error(request, "Access denied.")
        return redirect('account:login')
    
    vendor = request.user.vendor
    query = request.GET.get('q', '').strip()
    
    patients = Patient.objects.none()
    
    if query:
        # Search by patient ID, name, email, phone
        patients = Patient.objects.filter(
            vendor=vendor
        ).filter(
            Q(patient_id__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(contact_email__icontains=query) |
            Q(contact_phone__icontains=query)
        ).annotate(
            total_tests=Count('requests'),
            last_test_date=Max('requests__created_at')
        ).order_by('-last_test_date')
        
        # Paginate results
        paginator = Paginator(patients, 20)
        page = request.GET.get('page', 1)
        patients = paginator.get_page(page)
    
    context = {
        'patients': patients,
        'query': query,
    }
    
    return render(request, 'clinician/patient_search.html', context)


@login_required
def my_patients_list(request):
    """View patients the clinician has a relationship with."""
    if request.user.role != 'clinician':
        messages.error(request, "Access denied.")
        return redirect('account:login')
    
    # Get patients with active relationships
    patients = Patient.objects.filter(
        clinician_relationships__clinician=request.user,
        clinician_relationships__is_active=True
    ).annotate(
        total_tests=Count('requests'),
        last_test_date=Max('requests__created_at')
    ).order_by('-last_test_date')
    
    # Pagination
    paginator = Paginator(patients, 25)
    page = request.GET.get('page', 1)
    patients = paginator.get_page(page)
    
    context = {'patients': patients}
    return render(request, 'clinician/my_patients.html', context)


@login_required
def patient_detail(request, patient_id):
    """View comprehensive patient information and test history."""
    if request.user.role != 'clinician':
        messages.error(request, "Access denied.")
        return redirect('account:login')
    
    vendor = request.user.vendor
    patient = get_object_or_404(Patient, patient_id=patient_id, vendor=vendor)
    
    # Check if clinician has access to this patient
    relationship, created = ClinicianPatientRelationship.objects.get_or_create(
        clinician=request.user,
        patient=patient,
        defaults={
            'relationship_type': 'consulting',
            'established_via': 'Patient record view',
            'is_active': True,
        }
    )
    
    if not relationship.can_view_results:
        messages.error(request, "You don't have permission to view this patient's records.")
        return redirect('clinician:patient_search')
    
    # Get test history
    test_requests = TestRequest.objects.filter(
        patient=patient
    ).select_related('ordering_clinician').prefetch_related('requested_tests').order_by('-created_at')
    
    # Separate by status
    pending_tests = test_requests.filter(status__in=['P', 'R', 'A'])
    completed_tests = test_requests.filter(status__in=['C', 'V'])
    
    context = {
        'patient': patient,
        'relationship': relationship,
        'pending_tests': pending_tests,
        'completed_tests': completed_tests[:10],  # Last 10 completed
        'total_tests': test_requests.count(),
    }
    
    return render(request, 'clinician/patient_detail.html', context)


@login_required
def patient_test_history(request, patient_id):
    """Full test history for a patient."""
    if request.user.role != 'clinician':
        messages.error(request, "Access denied.")
        return redirect('account:login')
    
    vendor = request.user.vendor
    patient = get_object_or_404(Patient, patient_id=patient_id, vendor=vendor)
    
    # Verify access
    try:
        relationship = ClinicianPatientRelationship.objects.get(
            clinician=request.user,
            patient=patient,
            is_active=True
        )
        if not relationship.can_view_history:
            raise ClinicianPatientRelationship.DoesNotExist
    except ClinicianPatientRelationship.DoesNotExist:
        messages.error(request, "Access denied to patient history.")
        return redirect('clinician:patient_search')
    
    # Get all test requests
    test_requests = TestRequest.objects.filter(
        patient=patient
    ).select_related('ordering_clinician').prefetch_related('requested_tests').order_by('-created_at')
    
    # Filter by status if requested
    status_filter = request.GET.get('status')
    if status_filter:
        test_requests = test_requests.filter(status=status_filter)
    
    # Pagination
    paginator = Paginator(test_requests, 20)
    page = request.GET.get('page', 1)
    test_requests = paginator.get_page(page)
    
    context = {
        'patient': patient,
        'test_requests': test_requests,
        'status_filter': status_filter,
    }
    
    return render(request, 'clinician/patient_test_history.html', context)


