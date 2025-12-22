from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.db import transaction
from apps.labs.models import VendorTest, TestRequest, Department
from .forms import PatientProfileForm, PatientTestOrderForm
from .models import PatientUser
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


# TEST REQUEST AND ORDER 
@login_required
def patient_test_catalog(request):
    """Browse tests available for patient self-ordering."""
    try:
        patient_user = request.user.patient_profile
        patient = patient_user.patient
    except PatientUser.DoesNotExist:
        messages.error(request, "Patient profile not found.")
        return redirect('account:login')
    
    vendor = request.user.vendor
    
    # Get patient-accessible tests
    tests = VendorTest.objects.filter(
        vendor=vendor,
        enabled=True,
        available_for_online_booking=True
    ).select_related('assigned_department')
    
    # Search
    query = request.GET.get('q')
    if query:
        tests = tests.filter(
            Q(name__icontains=query) |
            Q(code__icontains=query) |
            Q(patient_friendly_description__icontains=query)
        )
    
    # Department filter
    department_id = request.GET.get('department')
    if department_id:
        tests = tests.filter(assigned_department_id=department_id)
    
    # Pagination
    paginator = Paginator(tests, 12)
    page = request.GET.get('page', 1)
    tests = paginator.get_page(page)

    departments = Department.objects.filter(
        vendor=vendor,
        tests__available_for_online_booking=True
    ).distinct()
    
    context = {
        'tests': tests,
        'query': query,
        'departments': departments,
        'patient': patient,
    }
    
    return render(request, 'patient/test_order/test_catalog.html', context)

# ============================================
# PATIENT ORDER VIEW
# ============================================

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .models import PatientUser

@login_required
def patient_create_order(request):
    """Patient creates a test order for themselves."""
    
    # Verify user is a patient
    if not hasattr(request.user, 'role') or request.user.role != 'patient':
        messages.error(request, "Access denied. This page is for patients only.")
        return redirect('dashboard')
    
    # Get patient profile
    try:
        patient_user = request.user.patient_profile
        patient = patient_user.patient
    except (AttributeError, PatientUser.DoesNotExist):
        messages.error(
            request,
            "Patient profile not found. Please complete your profile setup first."
        )
        return redirect('patients:profile_setup')
    
    # Get vendor - try multiple sources
    vendor = None
    if hasattr(request.user, 'vendor') and request.user.vendor:
        vendor = request.user.vendor
    elif hasattr(request, 'tenant') and request.tenant:
        vendor = request.tenant
    elif patient.vendor:
        vendor = patient.vendor
    
    if not vendor:
        messages.error(
            request,
            "Unable to determine laboratory. Please contact support."
        )
        return redirect('patients:dashboard')
    
    # DEBUG logging
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Patient order - User: {request.user.email}, Vendor: {vendor.name}")
    
    if request.method == 'POST':
        form = PatientTestOrderForm(
            request.POST,
            user=request.user,
            vendor=vendor
        )
        
        if form.is_valid():
            try:
                test_request = form.save()
                
                # Check if requires approval
                if test_request.requires_approval:
                    messages.info(
                        request,
                        f"✓ Test request {test_request.request_id} submitted successfully! "
                        "Your request requires physician review before processing. "
                        "We'll notify you once it's approved."
                    )
                else:
                    messages.success(
                        request,
                        f"✓ Test request {test_request.request_id} created successfully! "
                        "Please proceed to schedule your sample collection."
                    )
                
                return redirect('patients:order_detail', request_id=test_request.request_id)
            
            except Exception as e:
                logger.error(f"Error creating patient order: {e}", exc_info=True)
                messages.error(
                    request,
                    f"⚠ An error occurred while creating your order: {str(e)}"
                )
        else:
            messages.error(
                request,
                "⚠ Please correct the errors below before submitting."
            )
    else:
        form = PatientTestOrderForm(
            user=request.user,
            vendor=vendor
        )
        
        # Check if any tests are available
        available_tests_count = form.fields['requested_tests'].queryset.count()
        
        if available_tests_count == 0:
            messages.warning(
                request,
                "⚠ No tests are currently available for online booking. "
                "Please contact the laboratory for assistance."
            )
    
    context = {
        'form': form,
        'patient': patient,
        'vendor': vendor,
        'available_tests_count': form.fields['requested_tests'].queryset.count(),
    }
    
    return render(request, 'patient/test_order/order_create.html', context)


@login_required
def patient_order_detail(request, request_id):
    """View details of patient's test order."""
    try:
        patient_user = request.user.patient_profile
        patient = patient_user.patient
    except PatientUser.DoesNotExist:
        messages.error(request, "Patient profile not found.")
        return redirect('account:login')
    
    test_request = get_object_or_404(
        TestRequest,
        request_id=request_id,
        patient=patient
    )
    
    context = {
        'test_request': test_request,
        'patient': patient,
    }
    
    return render(request, 'patient/test_order/order_detail.html', context)


@login_required
def patient_order_list(request):
    """List all orders for this patient."""
    try:
        patient_user = request.user.patient_profile
        patient = patient_user.patient
    except PatientUser.DoesNotExist:
        messages.error(request, "Patient profile not found.")
        return redirect('account:login')
    
    orders = TestRequest.objects.filter(
        patient=patient
    ).prefetch_related('requested_tests').order_by('-created_at')
    
    # Filter by status
    status_filter = request.GET.get('status')
    if status_filter:
        orders = orders.filter(status=status_filter)
    
    # Pagination
    paginator = Paginator(orders, 10)
    page = request.GET.get('page', 1)
    orders = paginator.get_page(page)
    
    context = {
        'orders': orders,
        'patient': patient,
        'status_filter': status_filter,
    }
    
    return render(request, 'patient/test_order/order_list.html', context)


# ============== RESULT REQUEST ================

@login_required
def patient_view_results(request, request_id):
    """
    Patient views their test results.
    Only available if results are verified and released.
    """
    try:
        patient_user = request.user.patient_profile
        patient = patient_user.patient
    except PatientUser.DoesNotExist:
        messages.error(request, "Patient profile not found.")
        return redirect('account:login')
    
    test_request = get_object_or_404(
        TestRequest,
        request_id=request_id,
        patient=patient
    )
    
    # Check if results can be viewed
    if test_request.status != 'V':
        messages.warning(
            request, 
            "Results are not yet available. We'll notify you when ready."
        )
        return redirect('patient:order_detail', request_id=request_id)
    
    # Check if released to patient
    if not test_request.results_released_to_patient:
        messages.warning(
            request, 
            "Results are being reviewed by our medical team. You'll be notified when released."
        )
        return redirect('patient:order_detail', request_id=request_id)
    
    # Mark as viewed (first time only)
    if not test_request.patient_viewed_results_at:
        test_request.patient_viewed_results_at = timezone.now()
        test_request.save(update_fields=['patient_viewed_results_at'])
    
    # Get all results for this request
    results = TestResult.objects.filter(
        assignment__request=test_request,
        released=True
    ).select_related(
        'assignment',
        'assignment__lab_test',
        'assignment__lab_test__assigned_department'
    ).order_by('assignment__lab_test__name')
    
    # Check for critical values
    has_critical = results.filter(flag='C').exists()
    
    context = {
        'test_request': test_request,
        'patient': patient,
        'results': results,
        'has_critical': has_critical,
    }
    
    return render(request, 'patient/result/view_results.html', context)


@login_required
def patient_download_results(request, request_id):
    """Download results as text/PDF."""
    try:
        patient_user = request.user.patient_profile
        patient = patient_user.patient
    except PatientUser.DoesNotExist:
        messages.error(request, "Patient profile not found.")
        return redirect('account:login')
    
    test_request = get_object_or_404(
        TestRequest,
        request_id=request_id,
        patient=patient
    )
    
    # Verify results are released
    if not test_request.results_released_to_patient or test_request.status != 'V':
        messages.error(request, "Results are not available for download.")
        return redirect('patient:order_detail', request_id=request_id)
    
    # Get results
    results = TestResult.objects.filter(
        assignment__request=test_request,
        released=True
    ).select_related(
        'assignment__lab_test'
    )
    
    if not results.exists():
        messages.error(request, "No results available.")
        return redirect('patient:order_detail', request_id=request_id)
    
    # Generate text file (you can enhance to PDF later)
    content = generate_results_text(test_request, results, patient)
    
    response = HttpResponse(content, content_type='text/plain')
    response['Content-Disposition'] = f'attachment; filename="results-{request_id}.txt"'
    
    return response


def generate_results_text(test_request, results, patient):
    """Generate formatted text output of results."""
    from django.utils import timezone
    
    lines = [
        "=" * 60,
        f"LABORATORY TEST RESULTS",
        "=" * 60,
        "",
        f"Patient Name: {patient.first_name} {patient.last_name}",
        f"Patient ID: {patient.patient_id}",
        f"Date of Birth: {patient.date_of_birth}",
        f"Gender: {patient.get_gender_display()}",
        "",
        f"Order ID: {test_request.request_id}",
        f"Order Date: {test_request.created_at.strftime('%B %d, %Y')}",
        f"Report Date: {test_request.verified_at.strftime('%B %d, %Y %I:%M %p')}",
        "",
        "=" * 60,
        "TEST RESULTS",
        "=" * 60,
        "",
    ]
    
    # Group by department
    from itertools import groupby
    results_by_dept = groupby(
        results, 
        key=lambda r: r.assignment.lab_test.assigned_department
    )
    
    for department, dept_results in results_by_dept:
        lines.append(f"\n{department.name}")
        lines.append("-" * 60)
        
        for result in dept_results:
            test = result.assignment.lab_test
            lines.extend([
                f"\nTest: {test.name} ({test.code})",
                f"Result: {result.formatted_result}",
                f"Reference Range: {result.reference_range or 'N/A'}",
                f"Flag: {result.get_flag_display()}",
            ])
            
            if result.flag in ['C', 'H', 'L', 'A']:
                lines.append("⚠️  ABNORMAL - Please consult your healthcare provider")
            
            if result.remarks:
                lines.append(f"Remarks: {result.remarks}")
        
        lines.append("")
    
    lines.extend([
        "",
        "=" * 60,
        "IMPORTANT NOTES:",
        "- These results should be interpreted by a qualified healthcare provider",
        "- Do not use these results for self-diagnosis or treatment",
        "- Contact your doctor if you have questions or concerns",
        "",
        f"Report generated on: {timezone.now().strftime('%B %d, %Y %I:%M %p')}",
        f"Facility: {test_request.vendor.name}",
        "=" * 60,
    ])
    
    return "\n".join(lines)

