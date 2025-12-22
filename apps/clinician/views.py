"""
Operations/Task:
    Dashboard 
    Order Test 
    Get Patient Result -- Hooks and notifications

"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib import messages
from django.db.models import Q, Count, Max, Sum
from django.core.paginator import Paginator
from apps.labs.models import Patient, TestRequest, VendorTest, TestResult, Department
from .models import ClinicianProfile, ClinicianPatientRelationship
from .forms import ClinicianTestOrderForm, QuickTestOrderForm
from django.core.exceptions import PermissionDenied
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.http import JsonResponse
import json



def clinician_profile(request):
    vendor = request.user.vendor
    profile = ClinicianProfile.objects.get_or_create(vendor=vendor)
    return render(request, 'clinician/profile.html', {'profile':profile})


@login_required
def clinician_dashboard(request):
    if request.user.role != 'clinician':
        raise PermissionDenied

    clinician_profile = request.user.clinician_profile
    vendor = request.user.vendor

    my_patients = Patient.objects.filter(
        vendor=vendor,
        requests__ordering_clinician=request.user
    ).distinct()

    recent_orders = (
        TestRequest.objects
        .filter(vendor=vendor, ordering_clinician=request.user)
        .select_related('patient')
        .prefetch_related('requested_tests')
        .order_by('-created_at')[:10]
    )

    pending_results = TestResult.objects.filter(
        assignment__request__ordering_clinician=request.user,
        assignment__request__vendor=vendor,
        released=True,
        assignment__request__clinician_acknowledged_at__isnull=True
    ).count()

    critical_results = TestResult.objects.filter(
        assignment__request__ordering_clinician=request.user,
        assignment__request__vendor=vendor,
        released=True,
        flag='C',
        assignment__request__clinician_acknowledged_at__isnull=True
    ).count()

    context = {
        'clinician_profile': clinician_profile,
        'total_patients': my_patients.count(),
        'total_orders': recent_orders.count(),
        'pending_results': pending_results,
        'critical_results': critical_results,
        'recent_orders': recent_orders,
    }

    return render(request, 'clinician/dashboard.html', context)


# ========= PATIENT - RELATIONSHIP LOGIC ======== 

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
    
    return render(request, 'clinician/patient/patient_search.html', context)


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
    return render(request, 'clinician/patient/my_patients.html', context)


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
    

    total_orders = TestRequest.objects.filter(
        patient=patient, 
        vendor=vendor
    ).count()
    
    last_order = TestRequest.objects.filter(
        patient=patient, 
        vendor=vendor
    ).order_by('-created_at').first()

    # Separate by status
    pending_tests = test_requests.filter(status__in=['P', 'R', 'A'])
    completed_tests = test_requests.filter(status__in=['C', 'V'])
    
    context = {
        'patient': patient,
        'relationship': relationship,
        'pending_tests': pending_tests,
        'completed_tests': completed_tests[:10],  # Last 10 completed
        'total_tests': test_requests.count(),
        # addition 
        'total_orders': total_orders,
        'last_order_date': last_order.created_at if last_order else None,
    }
    
    return render(request, 'clinician/patient/patient_detail.html', context)


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
    
    return render(request, 'clinician/patient/patient_test_history.html', context)


# ================== TEST CATALOG ========================
@login_required
def test_catalog(request):
    """
    Browse full test catalog with search and filtering.
    """
    if request.user.role != 'clinician':
        messages.error(request, "Access denied.")
        return redirect('account:login')
    
    vendor = request.user.vendor
    
    # Get all enabled tests
    tests = VendorTest.objects.filter(
        vendor=vendor,
        enabled=True
    ).select_related('assigned_department')
    
    # Search functionality
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
    
    # Patient-accessible filter
    patient_accessible = request.GET.get('patient_accessible')
    if patient_accessible == 'yes':
        tests = tests.filter(available_for_online_booking=True)
    elif patient_accessible == 'no':
        tests = tests.filter(available_for_online_booking=False)
    
    # Pagination
    paginator = Paginator(tests, 25)
    page = request.GET.get('page', 1)
    tests = paginator.get_page(page)
    
    # Get departments for filter
    departments = Department.objects.filter(vendor=vendor)
    
    context = {
        'tests': tests,
        'query': query,
        'departments': departments,
        'selected_department': department_id,
        'patient_accessible': patient_accessible,
    }
    
    return render(request, 'clinician/test_order/test_catalog.html', context)


@login_required
def create_test_order(request, patient_id=None):
    """
    Create a new test order for a patient.
    Can be accessed with or without pre-selected patient.
    """
    if request.user.role != 'clinician':
        messages.error(request, "Access denied.")
        return redirect('account:login')
    
    vendor = request.user.vendor
    patient = None
    
    # If patient_id provided, pre-select patient
    if patient_id:
        patient = get_object_or_404(Patient, patient_id=patient_id, vendor=vendor)
        
        # Verify clinician has access
        try:
            relationship = ClinicianPatientRelationship.objects.get(
                clinician=request.user,
                patient=patient,
                is_active=True
            )
            if not relationship.can_order_tests:
                raise ClinicianPatientRelationship.DoesNotExist
        except ClinicianPatientRelationship.DoesNotExist:
            messages.error(request, "You don't have permission to order tests for this patient.")
            return redirect('clinicians:patient_search')
    
    if request.method == 'POST':
        form = ClinicianTestOrderForm(
            request.POST,
            user=request.user,
            vendor=vendor,
            patient=patient
        )
        
        if form.is_valid():
            test_request = form.save()
            
            messages.success(
                request,
                f"Test request {test_request.request_id} created successfully for "
                f"patient {test_request.patient.patient_id}."
            )
            
            # Redirect to request detail
            return redirect('clinician:test_request_detail', request_id=test_request.request_id)
    else:
        form = ClinicianTestOrderForm(
            user=request.user,
            vendor=vendor,
            patient=patient
        )
    
    context = {
        'form': form,
        'patient': patient,
    }
    
    return render(request, 'clinician/test_order/create_test_order.html', context)


@login_required
def quick_order_from_patient(request, patient_id):
    """
    Quick test order from patient detail page (AJAX-friendly).
    """
    if request.user.role != 'clinician':
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    vendor = request.user.vendor
    patient = get_object_or_404(Patient, patient_id=patient_id, vendor=vendor)
    
    if request.method == 'POST':
        form = QuickTestOrderForm(request.POST, vendor=vendor)
        
        if form.is_valid():
            # Create test request
            test_request = TestRequest.objects.create(
                vendor=vendor,
                patient=patient,
                requested_by=request.user,
                ordering_clinician=request.user,
                clinical_indication=form.cleaned_data['clinical_indication'],
                priority=form.cleaned_data['priority'],
                has_informed_consent=True,
            )
            
            # Add tests
            test_request.requested_tests.set(form.cleaned_data['tests'])
            
            # Update stats
            if hasattr(request.user, 'clinician_profile'):
                request.user.clinician_profile.increment_order_count()
            
            messages.success(request, f"Order {test_request.request_id} created successfully!")
            return redirect('clinicians:patient_detail', patient_id=patient_id)
    else:
        form = QuickTestOrderForm(vendor=vendor)
    
    context = {
        'form': form,
        'patient': patient,
    }
    
    return render(request, 'clinician/test_order/quick_order_modal.html', context)


@login_required
def test_request_detail(request, request_id):
    """View detailed information about a test request."""
    if request.user.role != 'clinician':
        messages.error(request, "Access denied.")
        return redirect('account:login')
    
    test_request = get_object_or_404(
        TestRequest.objects.select_related(
            'patient', 'ordering_clinician'
        ).prefetch_related(
            'requested_tests',
            'requested_tests__assigned_department',
            'test_results',
            'test_results__test',
            'activities'
        ),
        request_id=request_id,
        ordering_clinician=request.user
    )
    
    # Calculate total cost
    total_cost = test_request.requested_tests.aggregate(
        total=Sum('price')
    )['total'] or 0
    
    context = {
        'test_request': test_request,
        'total_cost': total_cost,
    }
    
    return render(request, 'clinician/test_order/test_request_detail.html', context)


@login_required
def my_orders(request):
    """List all test orders placed by this clinician."""
    if request.user.role != 'clinician':
        raise PermissionDenied("Accessed by Clinicians only")

    # Export functionality
    if request.GET.get('export') == 'csv':
        return export_orders_csv(test_requests)
    
    
    test_requests = TestRequest.objects.filter(
        ordering_clinician=request.user
    ).select_related('patient').prefetch_related('requested_tests').order_by('-created_at')
    
    # Filters
    status_filter = request.GET.get('status')
    patient_filter = request.GET.get('patient')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    priority_filter = request.GET.get('priority')
    
    if status_filter:
        test_requests = test_requests.filter(status=status_filter)
    
    if patient_filter:
        test_requests = test_requests.filter(patient__patient_id__icontains=patient_filter)
    
    if start_date:
        test_requests = test_requests.filter(created_at__date__gte=start_date)
    
    if end_date:
        test_requests = test_requests.filter(created_at__date__lte=end_date)
    
    if priority_filter:
        test_requests = test_requests.filter(priority=priority_filter)
    
    # Get status distribution
    from django.db.models import Count
    
    status_counts = {}
    for status_code, status_name in TestRequest.ORDER_STATUS:
        count = test_requests.filter(status=status_code).count()
        if count > 0:
            status_counts[status_code] = {
                'name': status_name,
                'count': count,
                'percentage': round((count / test_requests.count()) * 100) if test_requests.count() > 0 else 0
            }
    
    # Get recent activity (simplified version)
    recent_activity = []
    from django.utils import timezone
    from datetime import timedelta
    
    # Get recent status changes
    recent_status_changes = test_requests.filter(
        approved_at__gte=timezone.now() - timedelta(days=1)
    ).order_by('-approved_at')[:5]
    
    for request in recent_status_changes:
        recent_activity.append({
            'request_id': request.request_id,
            'description': f"Status changed to {request.get_status_display()}",
            'icon': get_icon_for_status(request.status),
            'time_ago': get_time_ago(request.updated_at)
        })
    
    # Pagination
    paginator = Paginator(test_requests, 20)
    page = request.GET.get('page', 1)
    test_requests = paginator.get_page(page)
    
    context = {
        'test_requests': test_requests,
        'status_filter': status_filter,
        'patient_filter': patient_filter,
        'status_distribution': status_counts,
        'recent_activity': recent_activity,
    }
    
    return render(request, 'clinician/test_order/my_orders.html', context)

# Helper functions
def get_icon_for_status(status):
    icons = {
        'pending': 'clock',
        'collected': 'syringe',
        'processing': 'flask',
        'completed': 'check-circle',
        'cancelled': 'times-circle',
    }
    return icons.get(status, 'bell')

def get_time_ago(dt):
    from django.utils import timezone
    from django.utils.timesince import timesince
    
    now = timezone.now()
    diff = now - dt
    
    if diff.total_seconds() < 60:
        return "Just now"
    elif diff.total_seconds() < 3600:
        minutes = int(diff.total_seconds() // 60)
        return f"{minutes}m ago"
    elif diff.total_seconds() < 86400:
        hours = int(diff.total_seconds() // 3600)
        return f"{hours}h ago"
    else:
        return timesince(dt) + " ago"
    

@login_required
@require_POST
def bulk_order_actions(request):
    """Handle bulk actions on multiple orders."""
    if request.user.role != 'clinician':
        return JsonResponse({'success': False, 'error': 'Access denied'}, status=403)
    
    try:
        data = json.loads(request.body)
        action = data.get('action')
        order_ids = data.get('order_ids', [])
        
        if not action or not order_ids:
            return JsonResponse({'success': False, 'error': 'Missing action or order IDs'})
        
        # Get orders belonging to this clinician
        orders = TestRequest.objects.filter(
            request_id__in=order_ids,
            ordering_clinician=request.user
        )
        
        if orders.count() != len(order_ids):
            return JsonResponse({'success': False, 'error': 'Some orders not found or access denied'})
        
        # Handle different actions
        if action == 'download_results':
            # Generate PDF for completed orders
            completed_orders = orders.filter(status='completed')
            if completed_orders.exists():
                # In a real implementation, you'd generate PDF here
                return JsonResponse({
                    'success': True, 
                    'message': f'PDF generation started for {completed_orders.count()} completed orders'
                })
            else:
                return JsonResponse({
                    'success': False, 
                    'error': 'No completed orders selected'
                })
                
        elif action == 'send_reminders':
            # Send reminders for pending/collected orders
            pending_orders = orders.filter(status__in=['pending', 'collected'])
            count = pending_orders.count()
            
            # In a real implementation, you'd send emails here
            # For now, just return success
            return JsonResponse({
                'success': True, 
                'message': f'Reminders sent for {count} orders'
            })
            
        elif action == 'generate_invoices':
            # Generate invoices for orders without them
            unpaid_orders = orders.filter(payment_status__in=['pending', 'unpaid'])
            count = unpaid_orders.count()
            
            # In a real implementation, you'd generate invoices here
            return JsonResponse({
                'success': True, 
                'message': f'Invoices generated for {count} orders'
            })

        elif action == 'cancel_orders':
            # Cancel selected orders (only if they're not completed)
            cancellable_orders = orders.exclude(status='completed')
            cancelled_count = 0
            
            for order in cancellable_orders:
                if order.status != 'cancelled':
                    order.status = 'cancelled'
                    order.save()
                    cancelled_count += 1
            
            return JsonResponse({
                'success': True, 
                'message': f'Cancelled {cancelled_count} orders'
            })
        
        else:
            return JsonResponse({'success': False, 'error': 'Invalid action'})
            
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


def export_orders_csv(queryset):
    import csv
    from django.http import HttpResponse
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="my_orders.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Order ID', 'Patient ID', 'Patient Name', 'Status', 
                     'Created Date', 'Number of Tests', 'Total Cost', 'Priority'])
    
    for order in queryset:
        writer.writerow([
            order.request_id,
            order.patient.patient_id,
            f"{order.patient.first_name} {order.patient.last_name}",
            order.get_status_display(),
            order.created_at.strftime('%Y-%m-%d %H:%M'),
            order.requested_tests.count(),
            order.calculate_total(),
            order.get_priority_display()
        ])
    
    return response


@login_required
@require_POST
def cancel_test_request(request, request_id):
    """Cancel a single test request."""
    if request.user.role != 'clinician':
        return JsonResponse({'success': False, 'error': 'Access denied'}, status=403)
    
    try:
        test_request = TestRequest.objects.get(
            request_id=request_id,
            ordering_clinician=request.user
        )
        
        if test_request.status == 'completed':
            return JsonResponse({'success': False, 'error': 'Cannot cancel completed orders'})
        
        test_request.status = 'cancelled'
        test_request.save()
        
        return JsonResponse({'success': True, 'message': 'Order cancelled successfully'})
        
    except TestRequest.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Order not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


# ================ RESULT FETCHING ==================
def clinician_results_queryset(user):
    """
    Base queryset for clinician-accessible test results.
    """
    return (
        TestResult.objects
        .select_related(
            "assignment",
            "assignment__request",
            "assignment__lab_test",
            "assignment__request__patient",
        )
        .filter(
            assignment__request__ordering_clinician=user,
            released=True,
        )
        .order_by(
            "-assignment__request__created_at",
            "assignment__lab_test__name",
        )
    )


@login_required
def clinician_result_list(request):
    if request.user.role != "clinician":
        raise PermissionDenied

    results = clinician_results_queryset(request.user)

    # Group results by TestRequest
    requests_map = {}
    for result in results:
        test_request = result.assignment.request
        requests_map.setdefault(test_request, []).append(result)

    context = {
        "requests_map": requests_map,
    }
    return render(request, "clinician/result/result_list.html", context)


@login_required
def clinician_result_detail(request, request_id):
    """
    Detailed view of a single order's results.
    """
    if request.user.role != 'clinician':
        raise PermissionDenied
    
    test_request = get_object_or_404(
        TestRequest.objects.select_related('patient', 'ordering_clinician'),
        request_id=request_id,
        ordering_clinician=request.user
    )
    
    # Get all results
    results = TestResult.objects.filter(
        assignment__request=test_request,
        released=True
    ).select_related(
        'assignment__lab_test',
        'assignment__lab_test__assigned_department'
    ).order_by('assignment__lab_test__name')
    
    # Check for critical
    has_critical = results.filter(flag='C').exists()
    critical_results = results.filter(flag='C')
    
    context = {
        'test_request': test_request,
        'results': results,
        'has_critical': has_critical,
        'critical_results': critical_results,
    }
    
    return render(request, 'clinician/result/result_detail.html', context)

@login_required
@require_POST
def clinician_acknowledge_result(request, pk):
    if request.user.role != "clinician":
        raise PermissionDenied

    test_request = get_object_or_404(
        TestRequest,
        pk=pk,
        ordering_clinician=request.user,
    )

    if test_request.clinician_acknowledged_at:
        messages.warning(request, "Results already acknowledged.")
        return redirect("clinician_results")

    # Ensure all assigned tests have released results
    has_unreleased = test_request.assignments.filter(
        result__isnull=True
    ).exists() or test_request.assignments.filter(
        result__released=False
    ).exists()

    if has_unreleased:
        messages.error(request, "Cannot acknowledge incomplete results.")
        return redirect("clinician_results")

    test_request.clinician_acknowledged_at = timezone.now()
    test_request.clinician_acknowledged_by = request.user
    test_request.save(update_fields=[
        "clinician_acknowledged_at",
        "clinician_acknowledged_by",
    ])

    messages.success(request, "Results acknowledged successfully.")
    return redirect("clinician_results")


@login_required
def download_results(request, request_id):
    if request.user.role != "clinician":
        raise PermissionDenied

    test_request = get_object_or_404(
        TestRequest,
        request_id=request_id,
        ordering_clinician=request.user,
    )

    results = (
        TestResult.objects
        .select_related(
            "assignment__lab_test",
            "assignment__request__patient",
        )
        .filter(
            assignment__request=test_request,
            released=True,
        )
    )

    if not results.exists():
        messages.error(request, "No released results available.")
        return redirect("clinician_results")

    from django.http import HttpResponse
    from django.utils import timezone

    patient = test_request.patient

    content = [
        "LABORATORY TEST RESULTS",
        "=======================",
        f"Order ID: {test_request.request_id}",
        f"Patient: {patient.first_name} {patient.last_name}",
        f"Patient ID: {patient.patient_id}",
        f"Collected On: {test_request.created_at:%Y-%m-%d}",
        "",
        "RESULTS:",
        "--------",
    ]

    for result in results:
        test = result.assignment.lab_test
        content.extend([
            f"{test.name} ({test.code})",
            f"Result: {result.value}",
            f"Reference Range: {result.reference_range}",
            f"Flag: {result.get_flag_display() if result.flag else 'Normal'}",
            "",
        ])

    content.append(f"Generated on: {timezone.now():%Y-%m-%d %H:%M}")

    response = HttpResponse(
        "\n".join(content),
        content_type="text/plain",
    )
    response["Content-Disposition"] = (
        f'attachment; filename="results-{request_id}.txt"'
    )

    return response


@login_required
def patient_autocomplete(request):
    if request.user.role != "clinician":
        return JsonResponse({"results": []}, status=403)

    query = request.GET.get("q", "").strip()
    results = []

    if len(query) >= 2:
        patients = Patient.objects.filter(
            testrequest__ordering_clinician=request.user
        ).filter(
            Q(patient_id__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(contact_email__icontains=query) |
            Q(contact_phone__icontains=query)
        ).distinct()[:10]

        results = [
            {
                "id": p.patient_id,
                "name": f"{p.first_name} {p.last_name}",
                "patient_id": p.patient_id,
                "email": p.contact_email,
            }
            for p in patients
        ]

    return JsonResponse({"results": results})

