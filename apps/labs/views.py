# import libraries 
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponseForbidden
from functools import wraps
from .utils import check_tenant_access
from django.contrib import messages
from django.db import transaction
from django.urls import reverse_lazy, reverse
from .forms import (
    DepartmentForm,
    VendorLabTestForm,
    TestRequestForm,
    SampleForm
)
from .models import (
    VendorTest, 
    Patient,
    TestRequest,
    Sample,
    TestAssignment,
    Department,
    AuditLog,
    Equipment
)
from apps.tenants.models import Vendor
from apps.accounts.models import VendorProfile
from django.core.paginator import Paginator
from django.db.models import Count, F, Q, Avg, ExpressionWrapper, DurationField, Sum
from datetime import timedelta
from django.utils import timezone
import logging


# Logger instance
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)



# --- Decorator Definition ---
def tenant_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        tenant, is_platform_admin = check_tenant_access(request)
        if not tenant and not is_platform_admin:
            return HttpResponseForbidden("Access Denied: Tenant or User Mismatch.")
        # Attach resolved values to request for easy use in the view
        request.tenant = tenant
        request.is_platform_admin = is_platform_admin
        return view_func(request, *args, **kwargs)
    return _wrapped_view


# --- CRM Views ---
@login_required
@tenant_required
def dashboard(request):
    tenant = request.tenant
    is_platform_admin = request.is_platform_admin
    if is_platform_admin and not tenant:
        # Assuming you have a login URL or process for platform admins without a tenant
        # return redirect("platform_admin_select_tenant") 
        pass 

    # Fetch lab Departments for the header (as in your original code)
    try:
        lab_departments = tenant.departments.all().order_by('name')
    except AttributeError:
        lab_departments = []

    lab_name = getattr(tenant, 'business_name', tenant.name)
    now = timezone.now()

    # --- 1. Calculate Time Ranges for Filtering ---
    date_filter = request.GET.get("filter", "7days")
    
    if date_filter == "today":
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        previous_start_date = start_date - timedelta(days=1)
    elif date_filter == "30days":
        start_date = now - timedelta(days=30)
        previous_start_date = now - timedelta(days=60)
    else:  # Default to 7days
        start_date = now - timedelta(days=7)
        previous_start_date = now - timedelta(days=14)

    # --- 2. Fetch Dashboard Statistics ---
    # Base query for Assignments
    assignment_base_qs = TestAssignment.objects.filter(vendor=tenant)
    sample_base_qs = Sample.objects.filter(vendor=tenant)

    # 2.1. Pending Samples/Assignments (P, Q, I status within the current filter period)
    pending_assignments_count = assignment_base_qs.filter(
        status__in=['P', 'Q', 'I'],
        created_at__gte=start_date
    ).count()

    # 2.2. Unverified Results (Assignments that are Analyzed (A) but not Verified/Released (V/R))
    # Filtered by the current time period to keep the count relevant to the date filter
    unread_results_count = assignment_base_qs.filter(
        status__in=['A'], 
        updated_at__gte=start_date 
    ).count()

    # 2.3. Total Samples processed (for trends)
    current_samples_count = sample_base_qs.filter(collected_at__gte=start_date).count()
    previous_samples_count = sample_base_qs.filter(
        collected_at__gte=previous_start_date, 
        collected_at__lt=start_date
    ).count()

    # Trend calculation
    samples_trend_percent = 0
    if previous_samples_count > 0:
        samples_trend_percent = round(((current_samples_count - previous_samples_count) / previous_samples_count) * 100, 1)
    elif current_samples_count > 0:
        samples_trend_percent = 100.0
        
    # Determine trend direction
    trend_direction = "up" if samples_trend_percent >= 0 else "down"

    # 2.4. Monthly Samples (always 30 days)
    monthly_samples_count = sample_base_qs.filter(
        collected_at__gte=now - timedelta(days=30)
    ).count()
    
    # 2.5. Average TAT (from creation to verification/release)
    avg_tat_display = "N/A"
    tat_qs = assignment_base_qs.filter(status__in=['V', 'R']).annotate(
        tat_duration=ExpressionWrapper(
            F('verified_at') - F('created_at'),
            output_field=DurationField()
        )
    )
    avg_tat_result = tat_qs.aggregate(Avg('tat_duration'))['tat_duration__avg']

    if avg_tat_result:
        total_seconds = avg_tat_result.total_seconds()
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        # Format: e.g., 4h 30m
        avg_tat_display = f"{hours}h {minutes}m"
        
    # --- 3. Equipment Status (NEW SECTION) ---
    equipment_qs = Equipment.objects.filter(vendor=tenant).select_related('department')
    
    equipment_with_stats = equipment_qs.annotate(
        pending_tests=Count(
            'assignments',
            filter=Q(assignments__status__in=['P', 'Q', 'I'])
        ),
        total_tests_today=Count(
            'assignments',
            filter=Q(assignments__created_at__gte=now.replace(hour=0, minute=0, second=0, microsecond=0))
        )
    ).order_by('-status', 'name')
    
    dashboard_equipment = equipment_with_stats[:5]
    
    equipment_stats = {
        'total': equipment_qs.count(),
        'active': equipment_qs.filter(status='active').count(),
        'maintenance': equipment_qs.filter(status='maintenance').count(),
        'inactive': equipment_qs.filter(status='inactive').count(),
        'configured': equipment_qs.exclude(api_endpoint='').count(),
        'unconfigured': equipment_qs.filter(api_endpoint='').count(),
    }

    # --- 4. Pagination for Recent Samples ---
    samples_qs = Sample.objects.filter(vendor=tenant, collected_at__gte=start_date).order_by('-collected_at')
    paginator = Paginator(samples_qs, 10)
    page_number = request.GET.get("page")
    samples_page = paginator.get_page(page_number)

    context = {
        "vendor": tenant,
        "lab_name": lab_name,
        "vendor_domain": tenant.domains.first().domain_name if tenant.domains.exists() else 'N/A',
        "lab_departments": lab_departments,
        "samples": samples_page,
        "current_filter": date_filter,
        
        # New Statistics Context
        "pending_assignments_count": pending_assignments_count,
        "samples_in_period_count": current_samples_count,
        "samples_trend_percent": abs(samples_trend_percent),
        "samples_trend_direction": trend_direction,
        "avg_tat_display": avg_tat_display,
        "unread_results_count": unread_results_count,
        "monthly_samples_count": monthly_samples_count,

        # NEW: Equipment Context
        "dashboard_equipment": dashboard_equipment,
        "equipment_stats": equipment_stats,
    }
    return render(request, "laboratory/dashboard.html", context)


# lab view
@login_required
@tenant_required
def lab_assistants(request):
    tenant = request.tenant
    assistants = request.user._meta.model.objects.filter(vendor=tenant, role='lab_staff')
    return render(request, "labs/assistants.html", {"assistants": assistants})

# improvements: Vendor's Logo
@login_required
@tenant_required
def profile(request):
    return render(request,"labs/profile.html",
        {"vendor": request.tenant, "user": request.user}
    )


# ***********************
# Vendor Admin Management / CRUD Operation
# ***********************
"""
Operations: 
CRUD operations by Vendor Admins on Department and VendorTest model.
"""

# -------------------------------------------------
# DEPARTMENT CRUD
# -------------------------------------------------
@login_required
@tenant_required
def department_list(request):
    """List all departments belonging to current vendor."""
    tenant = getattr(request, "tenant", None)
    is_platform_admin = getattr(request, "is_platform_admin", False)

    if is_platform_admin and not tenant:
        departments = Department.objects.all()
    else:
        departments = Department.objects.filter(vendor=tenant)
    return render(request, "laboratory/departments/list.html", {"departments": departments})

@login_required
@tenant_required
def department_create(request):
    """Create a new department for vendor (or platform admin on behalf)."""
    tenant = getattr(request, "tenant", None)
    is_platform_admin = getattr(request, "is_platform_admin", False)

    if request.method == "POST":
        form = DepartmentForm(request.POST)
        if form.is_valid():
            department = form.save(commit=False)

            # Platform admin may choose vendor manually
            if is_platform_admin and "vendor_id" in request.POST:
                department.vendor = get_object_or_404(Vendor, id=request.POST.get("vendor_id"))
            else:
                department.vendor = tenant

            department.save()
            messages.success(request, f"Department '{department.name}' created successfully.")
            return redirect("labs:department_list")
    else:
        form = DepartmentForm()
    return render(request, "laboratory/departments/form.html", {"form": form, "action": "Create"})

@login_required
@tenant_required
def department_update(request, pk):
    """Edit an existing department."""
    tenant = getattr(request, "tenant", None)
    is_platform_admin = getattr(request, "is_platform_admin", False)

    department = get_object_or_404(Department, pk=pk)

    # Restrict access if not platform admin and not same vendor
    if not is_platform_admin and department.vendor != tenant:
        return HttpResponseForbidden("Access denied.")

    if request.method == "POST":
        form = DepartmentForm(request.POST, instance=department)
        if form.is_valid():
            form.save()
            messages.success(request, f"Department '{department.name}' updated successfully.")
            return redirect("labs:department_list")
    else:
        form = DepartmentForm(instance=department)

    return render(request, "laboratory/departments/form.html", {"form": form, "action": "Update"})

@login_required
@tenant_required
def department_delete(request, pk):
    """Delete a department."""
    tenant = getattr(request, "tenant", None)
    is_platform_admin = getattr(request, "is_platform_admin", False)
    department = get_object_or_404(Department, pk=pk)

    if not is_platform_admin and department.vendor != tenant:
        return HttpResponseForbidden("Access denied.")

    if request.method == "POST":
        department.delete()
        messages.success(request, f"Department '{department.name}' deleted successfully.")
        return redirect("labs:department_list")

    return render(request, "laboratory/departments/confirm_delete.html", {"object": department})


# *************
# Test
# *************
@login_required
@tenant_required
def test_list(request):
    """List lab tests for the current vendor."""
    tenant = getattr(request, "tenant", None)
    is_platform_admin = getattr(request, "is_platform_admin", False)

    if is_platform_admin and not tenant:
        tests = VendorTest.objects.all().select_related("assigned_department", "vendor")
    else:
        tests = VendorTest.objects.filter(vendor=tenant).select_related("assigned_department")

    return render(request, "laboratory/tests/list.html", {"tests": tests})

@login_required
@tenant_required
def test_create(request):
    """Create a vendor-scoped test."""
    tenant = getattr(request, "tenant", None)
    is_platform_admin = getattr(request, "is_platform_admin", False)

    "handle error: Integrity error"
    if request.method == "POST":
        form = VendorLabTestForm(request.POST, vendor=tenant)
        if form.is_valid():
            test = form.save(commit=False)

            if is_platform_admin and "vendor_id" in request.POST:
                test.vendor = get_object_or_404(Vendor, id=request.POST.get("vendor_id"))
            else:
                test.vendor = tenant

            test.save()
            messages.success(request, f"Test '{test.name}' added successfully.")
            return redirect("labs:test_list")
    else:
        form = VendorLabTestForm(vendor=tenant)

    # Add vendors for platform admin dropdown
    context = {"form": form, "action": "Create"}
    if is_platform_admin and not tenant:
        context["vendors"] = Vendor.objects.all()

    return render(request, "laboratory/tests/form.html", context)

@login_required
@tenant_required
def test_update(request, pk):
    """Update an existing vendor test."""
    tenant = getattr(request, "tenant", None)
    is_platform_admin = getattr(request, "is_platform_admin", False)
    test = get_object_or_404(VendorTest, pk=pk)

    if not is_platform_admin and test.vendor != tenant:
        return HttpResponseForbidden("Access denied.")

    if request.method == "POST":
        form = VendorLabTestForm(request.POST, instance=test, vendor=test.vendor)
        if form.is_valid():
            form.save()
            messages.success(request, f"Test '{test.name}' updated successfully.")
            return redirect("labs:test_list")
    else:
        form = VendorLabTestForm(instance=test, vendor=test.vendor)

    return render(request, "laboratory/tests/form.html", {"form": form, "action": "Update"})

@login_required
@tenant_required
def test_delete(request, pk):
    """Delete a vendor test."""
    tenant = getattr(request, "tenant", None)
    is_platform_admin = getattr(request, "is_platform_admin", False)
    test = get_object_or_404(VendorTest, pk=pk)

    if not is_platform_admin and test.vendor != tenant:
        return HttpResponseForbidden("Access denied.")

    if request.method == "POST":
        test.delete()
        messages.success(request, f"Test '{test.name}' deleted successfully.")
        return redirect("labs:test_list")

    return render(request, "laboratory/tests/confirm_delete.html", {"object": test})


" LABORATORY_TEST_OPERATION"
# # ***********************
# Phase 1: Test Requests: Test are collected with sample..
# Models involved are: Sample, TestRequest, TestAssignment
# CRUD 
# ***********************
from django.contrib.auth.decorators import user_passes_test

def is_lab_staff_or_admin(user):
    return user.role in ["vendor_admin", "lab_staff"]

@login_required
def test_request_list(request):
    vendor = getattr(request.user, "vendor", None) or getattr(request, "tenant", None)
    if not vendor:
        messages.error(request, "Vendor not found.")
        return redirect("dashboard")

    # Get all test requests for this vendor
    requests_qs = (
        TestRequest.objects.filter(vendor=vendor)
        .select_related("patient")
        .prefetch_related("samples")  # fetch related samples efficiently
        .order_by("-created_at")
    )

    # Optional filtering
    patient_name = request.GET.get("patient")
    status = request.GET.get("status")

    if patient_name:
        requests_qs = requests_qs.filter(patient__first_name__icontains=patient_name)
    if status:
        requests_qs = requests_qs.filter(status=status)

    context = {
        "requests": requests_qs,
    }
    return render(request, "laboratory/requests/list.html", context)

@login_required
def test_request_create(request):
    """
    Handles creation of a new Test Request along with linked Sample(s),
    Patient record, and TestAssignments.
    """
    vendor = getattr(request.user, 'vendor', None) or getattr(request, 'tenant', None)
    if not vendor:
        messages.error(request, "Vendor not found for this user.")
        return redirect('dashboard')

    if request.method == 'POST':
        request_form = TestRequestForm(request.POST, vendor=vendor)
        sample_form = SampleForm(request.POST)

        if request_form.is_valid() and sample_form.is_valid():
            try:
                with transaction.atomic():
                    # --- Handle patient (existing or new) ---
                    patient_data = request_form.cleaned_data.get('patient')
                    patient = None

                    if isinstance(patient_data, Patient):
                        patient = patient_data
                    elif patient_data is None:
                        first_name = request_form.cleaned_data.get('first_name')
                        last_name = request_form.cleaned_data.get('last_name')
                        if not first_name or not last_name:
                            raise ValueError("Missing patient information: first name and last name are required.")

                        patient = Patient.objects.create(
                            vendor=vendor,
                            first_name=first_name,
                            last_name=last_name,
                            date_of_birth=request_form.cleaned_data.get('date_of_birth'),
                            gender=request_form.cleaned_data.get('gender'),
                            contact_email=request_form.cleaned_data.get('contact_email'),
                            contact_phone=request_form.cleaned_data.get('contact_phone'),
                        )
                    else:
                        raise ValueError("Invalid patient data provided.")

                    # --- Create Test Request ---
                    tests_to_order = request_form.cleaned_data['tests_to_order']
                    request_instance = request_form.save(commit=False)
                    request_instance.vendor = vendor
                    request_instance.requested_by = request.user
                    request_instance.patient = patient
                    request_instance.request_id = f"REQ-{vendor.requests.count() + 1:04d}"
                    request_instance.save()
                    request_instance.requested_tests.set(tests_to_order)

                    # --- Create Sample from form ---
                    sample = sample_form.save(commit=False)
                    sample.vendor = vendor
                    sample.patient = patient
                    sample.test_request = request_instance
                    sample.sample_id = f"SMP-{vendor.samples.count() + 1:06d}"
                    sample.save()

                    # --- Create Test Assignments ---
                    assignments = [
                        TestAssignment(
                            vendor=vendor,
                            request=request_instance,
                            lab_test=vendor_test,
                            sample=sample,
                            department=vendor_test.assigned_department,
                        )
                        for vendor_test in tests_to_order
                    ]
                    TestAssignment.objects.bulk_create(assignments)

                    messages.success(
                        request,
                        f"Request {request_instance.request_id} created successfully for "
                        f"{patient.first_name} {patient.last_name}."
                    )
                    return redirect('labs:test_request_list')

            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Error creating test request: {e}", exc_info=True)
                messages.error(request, f"An unexpected error occurred: {e}")

        else:
            messages.error(request, "Please correct the errors in the forms below.")
    else:
        request_form = TestRequestForm(vendor=vendor)
        sample_form = SampleForm()

    return render(request, 'laboratory/requests/form.html', {
        'form': request_form,
        'sample_form': sample_form,
    })

@login_required
def test_request_update(request, pk):
    vendor = getattr(request.user, "vendor", None)
    request_instance = get_object_or_404(TestRequest, pk=pk, vendor=vendor)

    # Get sample if it exists
    sample = Sample.objects.filter(test_request=request_instance).first()

    if request.method == "POST":
        form = TestRequestForm(request.POST, instance=request_instance, vendor=vendor)
        sample_form = SampleForm(request.POST, instance=sample)

        if form.is_valid() and sample_form.is_valid():
            try:
                with transaction.atomic():
                    updated_request = form.save(commit=False)
                    updated_request.vendor = vendor
                    updated_request.save()

                    # Update M2M ordered tests
                    updated_request.requested_tests.set(form.cleaned_data["tests_to_order"])

                    # Save sample info
                    sample_form.instance.test_request = updated_request
                    sample_form.save()

                    messages.success(request, f"{updated_request.request_id} updated successfully.")
                    return redirect("labs:test_request_list")

            except Exception as e:
                messages.error(request, f"Error updating request: {e}")

    else:
        # GET — instantiate both forms
        form = TestRequestForm(instance=request_instance, vendor=vendor)
        sample_form = SampleForm(instance=sample)

    return render(request, "laboratory/requests/form.html", {
        "form": form,
        "sample_form": sample_form,
        "update_mode": True,
    })

@login_required
@user_passes_test(is_lab_staff_or_admin)
def test_request_delete(request, pk):
    vendor = getattr(request.user, "vendor", None)
    request_instance = get_object_or_404(TestRequest, pk=pk, vendor=vendor)

    if request.method == "POST":
        request_instance.delete()
        messages.success(request, f"Request {request_instance.request_id} deleted successfully.")
        return redirect("test_request_list")

    return render(request, "labs/requests/test_request_confirm_delete.html", {
        "request_instance": request_instance
    })

@login_required
def test_request_detail(request, pk):
    """Display a detailed view of a test request with patient, billing, lab profile, and sample info."""
    vendor = getattr(request.user, "vendor", None)
    test_request = get_object_or_404(
        TestRequest.objects.select_related("patient", "vendor"), 
        pk=pk, 
        vendor=vendor
    )

    # Get vendor/lab profile
    vendor_profile = getattr(vendor, "profile", None)

    # Associated data
    requested_tests = test_request.requested_tests.all().select_related("assigned_department")
    samples = test_request.samples.all().select_related("patient")
    assignments = test_request.assignments.select_related("lab_test", "sample", "department")

    # Compute billing info
    total_cost = requested_tests.aggregate(total=Sum("price"))["total"] or 0.00
    payment_mode = getattr(test_request, "payment_mode", "Not Specified")

    # Status
    status_labels = dict(TestRequest.ORDER_STATUS)
    status_display = status_labels.get(test_request.status, "Unknown")

    context = {
        "vendor": vendor,
        "vendor_profile": vendor_profile,
        "test_request": test_request,
        "requested_tests": requested_tests,
        "samples": samples,
        "assignments": assignments,
        "total_cost": total_cost,
        "payment_mode": payment_mode,
        "status_display": status_display,
    }
    return render(request, "laboratory/requests/test_detail.html", context)


# **************
# Phase 2: Sample Examination                 
# **************
@login_required
def sample_examination_list(request):
    """List all samples awaiting verification or processing."""
    samples = Sample.objects.filter(status__in=['AC', 'RJ', 'AP']).select_related('patient', 'test_request')
    return render(request, 'laboratory/examination/sample_list.html', {'samples': samples})

@login_required
def sample_examination_detail(request, sample_id):
    """Detail view for verifying a specific sample."""
    sample = get_object_or_404(
        Sample.objects.select_related('test_request','test_request__patient', 'vendor'
        ).prefetch_related('test_request__requested_tests'),
        sample_id=sample_id
    )

    if request.method == 'POST':
        action = request.POST.get('action')
        reason = request.POST.get('reason', '')

        # Technician actions
        if action == 'verify':
            sample.verify_sample(request.user)
            messages.success(request, f"Sample {sample.sample_id} has been verified successfully.")
            return redirect(reverse('labs:sample-exam-detail', args=[sample.sample_id]))

        elif action == 'accept':
            sample.accept_sample(request.user)
            messages.success(request, f"Sample {sample.sample_id} accepted and queued for analysis.")
            return redirect('labs:sample-exam-list')

        elif action == 'reject':
            sample.reject_sample(request.user, reason)
            messages.warning(request, f"Sample {sample.sample_id} rejected.")
            return redirect('labs:sample-exam-list')

    return render(request, 'laboratory/examination/sample_detail.html', {'sample': sample})

# *******************
# Download TestRequest Form (WEASYPRINT VERSION)
# *******************
from django.template.loader import render_to_string
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
from django.db.models import Sum
from django.conf import settings
import weasyprint

from .models import TestRequest
from .utils import generate_barcode_base64

# NOTE: The render_to_pdf utility function has been removed. 
# WeasyPrint is simple enough to use directly in the view.

@login_required
def download_test_request(request, pk=None, blank=False):
    """
    Download a filled or blank Test Request form as PDF using WeasyPrint...
    """
    vendor = getattr(request.user, "vendor", None)
    vendor_profile = getattr(vendor, "profile", None)
    
    # Handle missing logo gracefully
    if vendor_profile and not vendor_profile.logo:
        vendor_profile.logo = None

    if blank:
        # Blank form version
        context = {
            "vendor": vendor,
            "vendor_profile": vendor_profile,
            "blank": True,
        }
        filename = f"Blank_Test_Request_Form.pdf"
    else:
        # Filled form version
        test_request = get_object_or_404(TestRequest, pk=pk, vendor=vendor)

        requested_tests = test_request.requested_tests.select_related("assigned_department")
        samples = test_request.samples.all()
        total_cost = requested_tests.aggregate(total=Sum("price"))["total"] or 0.00
        payment_mode = getattr(test_request, "payment_mode", "Not Specified")

        # Generate barcode
        barcode_image = generate_barcode_base64(test_request.request_id)

        context = {
            "vendor": vendor,
            "vendor_profile": vendor_profile,
            "test_request": test_request,
            "requested_tests": requested_tests,
            "samples": samples,
            "total_cost": total_cost,
            "payment_mode": payment_mode,
            "barcode_image": barcode_image,
            "blank": False,
        }
        filename = f"TestRequest_{test_request.request_id}.pdf"

    # Render the HTML template to a string
    html_string = render_to_string("laboratory/requests/pdf_template.html", context)

    # Prepare the HttpResponse
    response = HttpResponse(content_type='application/pdf')
    # Use 'attachment' to force download, or 'inline' to open in browser tab first
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    # --- WEASYPRINT GENERATION ---
    
    # Determine the base URL so WeasyPrint can find local images (like media/static)
    # request.build_absolute_uri('/') gives you e.g., http://localhost:8000/ or https://yourdomain.com/
    base_url = request.build_absolute_uri('/')

    try:
        # Create the HTML object with base_url for asset resolution
        html_obj = weasyprint.HTML(string=html_string, base_url=base_url)
        
        # Write the PDF directly to the response object (which acts like a file)
        html_obj.write_pdf(target=response)
        
        return response
        
    except Exception as e:
        # Log the actual error in development so you can see it in the console
        print(f"WeasyPrint Error: {e}")
        # In production, you might want to log this properly and return a generic error page
        return HttpResponse(f"Error generating PDF: {e}", status=500)



# **************************************************
# Phase 3:
# Post Examination Section
# ---- Post test, get result, and prepare result 
    # TestAssignment → represents a job sent to the instrument.
    # TestResult → holds result data.
    # VendorTest → defines reference range (min/max).
# ***************************************************
# ******************
# Test Assignment
# ******************

from django.views.decorators.http import require_POST, require_http_methods
from django.db import transaction
from django.core.exceptions import ValidationError
from .models import TestAssignment, TestResult, Equipment, AuditLog
from .services import (
    InstrumentService, 
    InstrumentAPIError,
    send_assignment_to_instrument,
    fetch_assignment_result
)

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.http import JsonResponse
from django.db import transaction
from django.core.paginator import Paginator
from django.db.models import Q, Prefetch
from django.utils import timezone
import json
import logging

from .models import TestAssignment, TestResult, Equipment, Department, AuditLog

logger = logging.getLogger(__name__)


from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Count, Prefetch
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from .models import TestAssignment, TestResult, QualitativeOption, AuditLog, Department, Equipment
from .services import send_assignment_to_instrument, InstrumentAPIError
from django.views.decorators.http import require_http_methods
from django.db import transaction
from django.utils import timezone

from decimal import Decimal, InvalidOperation
import logging


logger = logging.getLogger(__name__)



@login_required
def test_assignment_list(request):
    """
    List all test assignments with filtering, search, instrument assignment, and bulk actions.
    """
    vendor = request.user.vendor
    
    # Base queryset with optimized queries
    assignments = TestAssignment.objects.filter(
        vendor=vendor
    ).select_related(
        'lab_test',
        'request__patient',
        'sample',
        'instrument',
        'department',
        'assigned_to'
    ).prefetch_related(
        Prefetch('result', queryset=TestResult.objects.select_related('entered_by', 'verified_by'))
    )
    
    # Get filter parameters
    status_filter = request.GET.get('status', '')
    department_filter = request.GET.get('department', '')
    instrument_filter = request.GET.get('instrument', '')
    priority_filter = request.GET.get('priority', '')
    search_query = request.GET.get('search', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    
    # Apply filters
    if status_filter:
        assignments = assignments.filter(status=status_filter)
    
    if department_filter:
        assignments = assignments.filter(department_id=department_filter)
    
    if instrument_filter:
        if instrument_filter == 'unassigned':
            assignments = assignments.filter(instrument__isnull=True)
        else:
            assignments = assignments.filter(instrument_id=instrument_filter)
    
    if priority_filter:
        assignments = assignments.filter(request__priority=priority_filter)
    
    if search_query:
        assignments = assignments.filter(
            Q(request__request_id__icontains=search_query) |
            Q(request__patient__patient_id__icontains=search_query) |
            Q(request__patient__first_name__icontains=search_query) |
            Q(request__patient__last_name__icontains=search_query) |
            Q(lab_test__name__icontains=search_query) |
            Q(lab_test__code__icontains=search_query) |
            Q(sample__sample_id__icontains=search_query)
        )
    
    if date_from:
        assignments = assignments.filter(created_at__gte=date_from)
    
    if date_to:
        assignments = assignments.filter(created_at__lte=date_to)
    
    # Get ordering
    order_by = request.GET.get('order_by', '-created_at')
    assignments = assignments.order_by(order_by)
    
    # Get statistics for dashboard cards
    stats = {
        'total': assignments.count(),
        'pending': assignments.filter(status='P').count(),
        'queued': assignments.filter(status='Q').count(),
        'in_progress': assignments.filter(status='I').count(),
        'completed': assignments.filter(status='A').count(),
        'verified': assignments.filter(status='V').count(),
        'rejected': assignments.filter(status='R').count(),
        # NEW: Unassigned instruments stat
        'unassigned_instruments': assignments.filter(
            status='P',
            instrument__isnull=True
        ).count(),
    }
    
    # Pagination
    paginator = Paginator(assignments, 25)  # 25 items per page
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    # Get filter options for dropdowns
    departments = Department.objects.filter(vendor=vendor)
    instruments = Equipment.objects.filter(vendor=vendor, status='active')
    
    # NEW: Get available instruments for quick assignment (active only)
    available_instruments = Equipment.objects.filter(
        vendor=vendor,
        status='active'
    ).select_related('department').order_by('department__name', 'name')
    
    context = {
        'page_obj': page_obj,
        'assignments': page_obj.object_list,
        'stats': stats,
        'departments': departments,
        'instruments': instruments,
        'available_instruments': available_instruments,  # NEW
        
        # Current filters (to maintain state)
        'current_status': status_filter,
        'current_department': department_filter,
        'current_instrument': instrument_filter,
        'current_priority': priority_filter,
        'search_query': search_query,
        'date_from': date_from,
        'date_to': date_to,
        'order_by': order_by,
        
        # Available options
        'status_choices': TestAssignment.ASSIGNMENT_STATUS,
        'priority_choices': [
            ('routine', 'Routine'),
            ('urgent', 'Urgent'),
            ('stat', 'STAT'),
        ],
    }
    
    return render(request, 'laboratory/assignment/test_assignment_list.html', context)


@login_required
def test_assignment_detail(request, assignment_id):
    """View detailed information about a test assignment"""
    assignment = get_object_or_404(
        TestAssignment.objects.select_related(
            'lab_test',
            'request__patient',
            'sample',
            'instrument',
            'department',
            'assigned_to'
        ).prefetch_related('instrument_logs'),
        id=assignment_id,
        vendor=request.user.vendor
    )
    
    # Get result if exists
    result = getattr(assignment, 'result', None)
    
    # Get communication logs
    logs = assignment.instrument_logs.all()[:10]
    
    context = {
        'assignment': assignment,
        'result': result,
        'logs': logs,
        'can_send': assignment.can_send_to_instrument(),
        'can_verify': (
            result and 
            not result.verified_at and 
            result.entered_by != request.user
        ),
        'can_release': result and result.verified_at and not result.released,
    }
    
    return render(request, 'laboratory/assignment/test_assignment_detail.html', context)

# ===== NEW: INSTRUMENT ASSIGNMENT VIEWS =====

@login_required
@require_POST
def assign_instrument(request, assignment_id):
    """
    Assign or reassign instrument to a test assignment (AJAX endpoint)
    """
    try:
        # Parse JSON body
        data = json.loads(request.body)
        instrument_id = data.get('instrument_id')
        
        # Get assignment
        assignment = get_object_or_404(
            TestAssignment,
            id=assignment_id,
            vendor=request.user.vendor
        )
        
        # Validation: Can only assign to pending/in-progress assignments
        if assignment.status not in ['P', 'I']:
            return JsonResponse({
                'success': False,
                'message': f'Cannot assign instrument. Test is in {assignment.get_status_display()} status.'
            }, status=400)
        
        # If already queued to instrument, prevent reassignment
        if assignment.status == 'Q':
            return JsonResponse({
                'success': False,
                'message': 'Cannot reassign. Test already queued to instrument.'
            }, status=400)
        
        with transaction.atomic():
            old_instrument = assignment.instrument
            
            if instrument_id:
                # Assign new instrument
                instrument = get_object_or_404(
                    Equipment,
                    id=instrument_id,
                    vendor=request.user.vendor
                )
                
                # Check instrument status
                if instrument.status != 'active':
                    return JsonResponse({
                        'success': False,
                        'message': f'Instrument {instrument.name} is not active.'
                    }, status=400)
                
                assignment.instrument = instrument
                action_text = f"Assigned to {instrument.name}"
                
            else:
                # Unassign instrument
                assignment.instrument = None
                action_text = "Unassigned instrument"
            
            assignment.save(update_fields=['instrument'])
            
            # Create audit log
            AuditLog.objects.create(
                vendor=request.user.vendor,
                user=request.user,
                action=(
                    f"Instrument assignment: {assignment.request.request_id} - "
                    f"{assignment.lab_test.code} | "
                    f"From: {old_instrument.name if old_instrument else 'None'} → "
                    f"To: {assignment.instrument.name if assignment.instrument else 'None'}"
                ),
                ip_address=request.META.get('REMOTE_ADDR')
            )
        
        return JsonResponse({
            'success': True,
            'message': action_text,
            'instrument_name': assignment.instrument.name if assignment.instrument else None
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'message': 'Invalid JSON data'
        }, status=400)
    
    except Exception as e:
        logger.error(f"Error assigning instrument: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=500)

@login_required
@require_POST
def send_to_instrument(request, assignment_id):
    """Send test assignment to instrument queue"""
    assignment = get_object_or_404(
        TestAssignment.objects.select_related('instrument', 'vendor', 'lab_test'),
        id=assignment_id,
        vendor=request.user.vendor  # Ensure multi-tenant security
    )
    
    # Validate assignment can be sent
    if not assignment.can_send_to_instrument():
        messages.error(
            request, 
            "Cannot send to instrument. Check instrument assignment and status."
        )
        return redirect('test_assignment_detail', assignment_id=assignment.id)
    
    try:
        result = send_assignment_to_instrument(assignment_id)
        
        # Log the action
        AuditLog.objects.create(
            vendor=assignment.vendor,
            user=request.user,
            action=f"Sent assignment {assignment.id} to instrument {assignment.instrument.name}",
            ip_address=request.META.get('REMOTE_ADDR')
        )
        
        messages.success(
            request, 
            f"Test sent to {assignment.instrument.name} successfully. Queue ID: {result.get('id')}"
        )
        
    except InstrumentAPIError as e:
        messages.error(request, f"Error sending to instrument: {str(e)}")
        logger.error(f"Failed to send assignment {assignment_id}: {e}")
    
    return redirect('test_assignment_detail', assignment_id=assignment.id)

@login_required
@require_http_methods(["GET", "POST"])
def fetch_result_from_instrument(request, assignment_id):
    """Manually trigger result fetch from instrument"""
    assignment = get_object_or_404(
        TestAssignment.objects.select_related('instrument', 'vendor'),
        id=assignment_id,
        vendor=request.user.vendor
    )
    
    # Check if already has result
    if hasattr(assignment, 'result') and assignment.result.verified_at:
        messages.warning(request, "This result has already been verified.")
        return redirect('test_assignment_detail', assignment_id=assignment.id)
    
    try:
        result = fetch_assignment_result(assignment_id)
        
        if result:
            AuditLog.objects.create(
                vendor=assignment.vendor,
                user=request.user,
                action=f"Fetched result for assignment {assignment.id} from instrument",
                ip_address=request.META.get('REMOTE_ADDR')
            )
            messages.success(request, "Result successfully retrieved and saved.")
        else:
            messages.info(request, "Result not yet available from instrument.")
            
    except InstrumentAPIError as e:
        messages.error(request, f"Error fetching result: {str(e)}")
        logger.error(f"Failed to fetch result for assignment {assignment_id}: {e}")
    
    return redirect('test_assignment_detail', assignment_id=assignment.id)


@login_required
@require_http_methods(["GET", "POST"])
def enter_manual_result(request, assignment_id):
    """
    Manually enter test result - handles both QUALITATIVE and QUANTITATIVE tests.

    Flow:
      - Validate assignment status and that result is not verified
      - For QLT: accept option ID (preferred) or free text (validated)
      - For QNT: accept numeric value and optional unit
      - Create or update TestResult, call auto_flag_result()
      - Mark assignment analyzed and create audit log
    """
    assignment = get_object_or_404(
        TestAssignment.objects.select_related(
            "lab_test", "vendor", "request__patient", "sample", "instrument"
        ),
        id=assignment_id,
        vendor=getattr(request.user, "vendor", None),
    )

    # --- Basic validation ---
    if assignment.status not in ["P", "Q", "I"]:
        messages.error(
            request,
            "Cannot enter result. Test must be Pending, Queued or In Progress.",
        )
        return redirect("laboratory:test_assignment_detail", assignment_id=assignment.id)

    if hasattr(assignment, "result") and assignment.result.verified_at:
        messages.error(
            request,
            "Cannot modify verified result. Contact supervisor for amendments.",
        )
        return redirect("laboratory:test_assignment_detail", assignment_id=assignment.id)

    lab_test = assignment.lab_test
    is_quantitative = lab_test.result_type == "QNT"
    is_qualitative = lab_test.result_type == "QLT"

    # POST: process submission
    if request.method == "POST":
        # Raw inputs
        raw_value = request.POST.get("result_value", "").strip()
        unit = request.POST.get("unit", "").strip()
        remarks = request.POST.get("remarks", "").strip()
        interpretation = request.POST.get("interpretation", "").strip()

        # For qualitative prefer selecting option ID
        selected_option = None
        if is_qualitative:
            option_id = request.POST.get("qualitative_option")
            if option_id:
                try:
                    selected_option = lab_test.qlt_options.get(id=int(option_id))
                    raw_value = selected_option.value
                except (QualitativeOption.DoesNotExist, ValueError):
                    messages.error(request, "Invalid qualitative option selected.")
                    # fall through to re-render form
                    selected_option = None

        # required value check
        if not raw_value:
            messages.error(request, "Result value is required.")
            # render below with context
        else:
            # Validate quantitative numeric input
            if is_quantitative:
                try:
                    numeric_value = Decimal(str(raw_value).strip())
                except (InvalidOperation, ValueError):
                    messages.error(request, f"Invalid numeric value: '{raw_value}'.")
                    numeric_value = None

                # optional heuristic warnings (not authoritative; auto_flag_result will set flags)
                if numeric_value is not None and lab_test.min_reference_value:
                    try:
                        if lab_test.min_reference_value and numeric_value < (lab_test.min_reference_value * Decimal("0.1")):
                            messages.warning(request, "Value unusually low — double-check entry.")
                    except Exception:
                        pass
                if numeric_value is not None and lab_test.max_reference_value:
                    try:
                        if lab_test.max_reference_value and numeric_value > (lab_test.max_reference_value * Decimal("10")):
                            messages.warning(request, "Value unusually high — double-check entry.")
                    except Exception:
                        pass

            # # If no errors so far, persist
            # if not messages.get_messages(request):  # no messages = no errors/warnings to block saving

            # Check specifically for errors
            from django.contrib.messages import get_messages, ERROR

            has_errors = any(m.level == ERROR for m in get_messages(request))
            if not has_errors:
                # Proceed with save
                try:
                    with transaction.atomic():
                        # get or create TestResult
                        result, created = TestResult.objects.get_or_create(
                            assignment=assignment,
                            defaults={
                                "data_source": "manual",
                                "entered_by": request.user,
                                "entered_at": timezone.now(),
                            },
                        )

                        # If existing and different value, use update_result to preserve audit trail
                        if not created and str(result.result_value).strip() != str(raw_value).strip():
                            # update_result checks verified_at and raises if not allowed
                            result.update_result(new_value=raw_value, user=request.user, reason=f"Manual correction")
                            # note: update_result already calls auto_flag_result inside your model,
                            # but we'll call auto_flag_result() again after setting other fields to guarantee consistency.
                        else:
                            result.result_value = raw_value

                        # Units
                        if is_quantitative:
                            result.units = unit or (lab_test.default_units or "")
                        else:
                            result.units = ""

                        # Qualitative option linking (if field exists on model)
                        if is_qualitative and selected_option:
                            # Only assign if TestResult model has attribute qualitative_option
                            if hasattr(result, "qualitative_option"):
                                result.qualitative_option = selected_option

                        # Reference range population
                        if is_quantitative:
                            if lab_test.min_reference_value is not None and lab_test.max_reference_value is not None:
                                result.reference_range = f"{lab_test.min_reference_value} - {lab_test.max_reference_value}"
                            else:
                                result.reference_range = ""
                        else:
                            # Build a friendly reference from normal qualitative options
                            normal_opts = lab_test.qlt_options.filter(is_normal=True).values_list("value", flat=True)
                            result.reference_range = ", ".join(normal_opts) if normal_opts else ""

                        # Other metadata
                        result.remarks = remarks
                        result.interpretation = interpretation
                        result.data_source = "manual"
                        result.entered_by = result.entered_by or request.user
                        # entered_at is auto_now_add; do not override normally

                        result.save()  # persist intermediate changes

                        # Apply auto-flagging using your engine (AMR, CRR, panic, ref range, qualitative)
                        result.auto_flag_result()

                        # Mark assignment analyzed (A)
                        assignment.mark_analyzed()

                        # Audit log
                        AuditLog.objects.create(
                            vendor=assignment.vendor,
                            user=request.user,
                            action=(
                                f"Manual result entered for {assignment.request.request_id} - "
                                f"{assignment.lab_test.code}: {result.result_value} "
                                f"{(' ' + result.units) if result.units else ''} "
                                f"[manual]"
                            ),
                            ip_address=request.META.get("REMOTE_ADDR"),
                        )

                        messages.success(request, f"Result saved. Flag: {result.get_flag_display()}. Awaiting verification.")
                        return redirect("laboratory:test_assignment_detail", assignment_id=assignment.id)

                except ValidationError as ve:
                    messages.error(request, f"Validation error: {ve}")
                    logger.exception("Validation error saving manual result")
                except Exception as e:
                    messages.error(request, f"Error saving result: {str(e)}")
                    logger.exception("Unexpected error saving manual result")

    # GET (or POST with errors) - prepare context for form rendering
    qualitative_options = lab_test.qlt_options.all() if is_qualitative else []
    existing_result = getattr(assignment, "result", None)

    context = {
        "assignment": assignment,
        "lab_test": lab_test,
        "is_quantitative": is_quantitative,
        "is_qualitative": is_qualitative,
        "qualitative_options": qualitative_options,
        "existing_result": existing_result,
        "default_unit": lab_test.default_units,
        "reference_range": (
            f"{lab_test.min_reference_value} - {lab_test.max_reference_value}"
            if is_quantitative and lab_test.min_reference_value is not None and lab_test.max_reference_value is not None
            else ", ".join(lab_test.qlt_options.filter(is_normal=True).values_list("value", flat=True)) if is_qualitative else ""
        ),
    }

    return render(request, "laboratory/result/manual_result_form.html", context)

# ===== RESULT DETAIL VIEW =====
@login_required
def result_list(request):
    """
    List all test results with filtering and search.
    Shows pending verification, verified, and released results.
    """
    vendor = request.user.vendor
    
    # Base queryset
    results = TestResult.objects.filter(
        assignment__vendor=vendor
    ).select_related(
        'assignment__lab_test',
        'assignment__request__patient',
        'assignment__instrument',
        'assignment__department',
        'entered_by',
        'verified_by',
        'released_by'
    ).order_by('-entered_at')
    
    # Filters
    status_filter = request.GET.get('status', '')
    flag_filter = request.GET.get('flag', '')
    source_filter = request.GET.get('source', '')
    department_filter = request.GET.get('department', '')
    search_query = request.GET.get('search', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    
    # Apply filters
    if status_filter == 'pending':
        results = results.filter(verified_at__isnull=True, released=False)
    elif status_filter == 'verified':
        results = results.filter(verified_at__isnull=False, released=False)
    elif status_filter == 'released':
        results = results.filter(released=True)
    elif status_filter == 'critical':
        results = results.filter(flag='C')
    elif status_filter == 'amended':
        results = results.filter(is_amended=True)
    
    if flag_filter:
        results = results.filter(flag=flag_filter)
    
    if source_filter:
        results = results.filter(data_source=source_filter)
    
    if department_filter:
        results = results.filter(assignment__department_id=department_filter)
    
    if search_query:
        results = results.filter(
            Q(assignment__request__request_id__icontains=search_query) |
            Q(assignment__request__patient__first_name__icontains=search_query) |
            Q(assignment__request__patient__last_name__icontains=search_query) |
            Q(assignment__lab_test__name__icontains=search_query) |
            Q(result_value__icontains=search_query)
        )
    
    if date_from:
        results = results.filter(entered_at__gte=date_from)
    
    if date_to:
        results = results.filter(entered_at__lte=date_to)
    
    # Statistics
    stats = {
        'total': results.count(),
        'pending_verification': results.filter(verified_at__isnull=True, released=False).count(),
        'verified': results.filter(verified_at__isnull=False, released=False).count(),
        'released': results.filter(released=True).count(),
        'critical': results.filter(flag='C').count(),
        'manual': results.filter(data_source='manual').count(),
        'instrument': results.filter(data_source='instrument').count(),
    }
    
    # Pagination
    paginator = Paginator(results, 30)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'stats': stats,
        'status_filter': status_filter,
        'flag_filter': flag_filter,
        'source_filter': source_filter,
        'department_filter': department_filter,
        'search_query': search_query,
        'date_from': date_from,
        'date_to': date_to,
    }
    
    return render(request, 'laboratory/result/result_list.html', context)

# @login_required
# def result_detail(request, result_id):
#     """
#     Display detailed view of a single result with full audit trail.
#     """
#     result = get_object_or_404(
#         TestResult.objects.select_related(
#             'assignment__lab_test',
#             'assignment__request__patient',
#             'assignment__request__ordered_by',
#             'assignment__instrument',
#             'assignment__department',
#             'assignment__sample',
#             'entered_by',
#             'verified_by',
#             'released_by'
#         ),
#         id=result_id,
#         assignment__vendor=request.user.vendor
#     )
    
#     # Get patient's previous results for same test (for trending)
#     previous_results = TestResult.objects.filter(
#         assignment__request__patient=result.assignment.request.patient,
#         assignment__lab_test=result.assignment.lab_test,
#         released=True
#     ).exclude(id=result.id).order_by('-entered_at')[:5]
    
#     # Check permissions
#     can_verify = (
#         request.user.has_perm('labs.can_verify_results') and
#         result.can_be_verified and
#         result.entered_by != request.user
#     )
    
#     can_release = (
#         request.user.has_perm('labs.can_release_results') and
#         result.can_be_released
#     )
    
#     can_amend = (
#         request.user.has_perm('labs.can_amend_results') and
#         result.released
#     )
    
#     can_edit = not result.verified_at and not result.released
    
#     context = {
#         'result': result,
#         'previous_results': previous_results,
#         'can_verify': can_verify,
#         'can_release': can_release,
#         'can_amend': can_amend,
#         'can_edit': can_edit,
#     }
    
#     return render(request, 'laboratory/results/result_detail.html', context)

@login_required
def result_detail(request, result_id):
    """
    Display detailed view of a single result with full audit trail.
    Includes permission checks for verify, release, and amend actions.
    """
    result = get_object_or_404(
        TestResult.objects.select_related(
            'assignment__lab_test',
            'assignment__request__patient',
            'assignment__request__ordered_by',
            'assignment__instrument',
            'assignment__department',
            'assignment__sample',
            'entered_by',
            'verified_by',
            'released_by'
        ),
        id=result_id,
        assignment__vendor=request.user.vendor  # ✅ Multi-tenant security
    )
    
    # Get patient's previous results for same test (for trending)
    previous_results = TestResult.objects.filter(
        assignment__request__patient=result.assignment.request.patient,
        assignment__lab_test=result.assignment.lab_test,
        released=True
    ).exclude(id=result.id).order_by('-entered_at')[:5]
    
    # ======================================================
    # ✅ PERMISSION CHECKS (using custom permissions)
    # ======================================================
    
    # Can verify: has permission + result state allows it + didn't enter it
    can_verify = (
        request.user.has_perm('laboratory.can_verify_results') and  # ✅ Custom permission
        result.can_be_verified and
        result.entered_by != request.user  # Prevent self-verification
    )
    
    # Can release: has permission + result is verified but not released
    can_release = (
        request.user.has_perm('laboratory.can_release_results') and  # ✅ Custom permission
        result.can_be_released
    )
    
    # Can amend: has permission + result is already released
    can_amend = (
        request.user.has_perm('laboratory.can_amend_results') and  # ✅ Custom permission
        result.released
    )
    
    # Can edit: result not yet verified or released (basic editing)
    can_edit = not result.verified_at and not result.released
    
    # ======================================================
    # CONTEXT FOR TEMPLATE
    # ======================================================
    
    context = {
        'result': result,
        'previous_results': previous_results,
        'can_verify': can_verify,
        'can_release': can_release,
        'can_amend': can_amend,
        'can_edit': can_edit,
        
        # Additional helpful context
        'is_critical': result.is_critical,
        'has_delta_check': result.delta_flag,
        'workflow_stage': _get_workflow_stage(result),
    }
    
    return render(request, 'laboratory/results/result_detail.html', context)


def _get_workflow_stage(result):
    """Helper to determine current workflow stage for display"""
    if result.released:
        return 'released'
    elif result.verified_at:
        return 'verified'
    elif result.entered_at:
        return 'entered'
    else:
        return 'pending'


@login_required
@require_http_methods(["GET", "POST"])
def edit_result(request, result_id):
    """
    Edit result before verification.
    Cannot edit verified or released results.
    """
    result = get_object_or_404(
        TestResult.objects.select_related(
            'assignment__lab_test',
            'assignment__request__patient'
        ),
        id=result_id,
        assignment__vendor=request.user.vendor
    )

    # --- PERMISSION CHECKS ---
    if result.verified_at:
        messages.error(request, "Cannot edit verified result. Contact supervisor for amendment.")
        return redirect('laboratory:result_detail', result_id=result.id)

    if result.released:
        messages.error(request, "Cannot edit released result. Use the amendment process.")
        return redirect('laboratory:result_detail', result_id=result.id)

    test_type = result.assignment.lab_test.result_type
    is_quantitative = test_type == 'QNT'

    if request.method == "POST":
        new_value = request.POST.get("result_value", "").strip()
        units = request.POST.get("units", "").strip()
        remarks = request.POST.get("remarks", "").strip()
        interpretation = request.POST.get("interpretation", "").strip()
        reason = request.POST.get("reason", "").strip()

        # --- Validation ---
        if not new_value:
            messages.error(request, "Result value is required.")
            return render(request, 'laboratory/results/edit_result.html', {
                'result': result,
                'is_quantitative': is_quantitative
            })

        if is_quantitative:
            try:
                Decimal(new_value)
            except:
                messages.error(request, "Invalid numeric value for quantitative test.")
                return render(request, 'laboratory/results/edit_result.html', {
                    'result': result,
                    'is_quantitative': is_quantitative
                })

        # --- SAVE LOGIC ---
        try:
            with transaction.atomic():

                # Handle amendment/versioning
                if result.result_value != new_value:
                    result.update_result(
                        new_value=new_value,
                        user=request.user,
                        reason=reason
                    )

                result.units = units if is_quantitative else ''
                result.remarks = remarks
                result.interpretation = interpretation
                result.save(update_fields=['units', 'remarks', 'interpretation'])

                # Re-run auto flagging
                result.auto_flag_result()

                # Delta checking
                result.check_delta()

                # Audit log
                AuditLog.objects.create(
                    vendor=request.user.vendor,
                    user=request.user,
                    action=(
                        f"Updated result for {result.assignment.request.request_id} - "
                        f"{result.assignment.lab_test.code}: {new_value}"
                    ),
                    ip_address=request.META.get('REMOTE_ADDR')
                )

                messages.success(request, "Result updated successfully.")
                return redirect('laboratory:result_detail', result_id=result.id)

        except Exception as e:
            logger.error(f"Error updating result: {e}", exc_info=True)
            messages.error(request, f"Error: {str(e)}")

    return render(request, 'laboratory/results/edit_result.html', {
        'result': result,
        'is_quantitative': is_quantitative,
        'action': 'Edit'
    })


@login_required
@require_POST
def verify_result(request, assignment_id):
    """Verify a completed test result"""
    assignment = get_object_or_404(
        TestAssignment.objects.select_related('vendor'),
        id=assignment_id,
        vendor=request.user.vendor
    )
    
    if not hasattr(assignment, "result"):
        messages.error(request, "No result found to verify.")
        return redirect('test_assignment_detail', assignment_id=assignment.id)
    
    result = assignment.result
    
    # Check if already verified
    if result.verified_at:
        messages.warning(request, "This result has already been verified.")
        return redirect('test_assignment_detail', assignment_id=assignment.id)
    
    # Prevent self-verification (optional policy)
    if result.entered_by == request.user:
        messages.error(request, "You cannot verify results you entered yourself.")
        return redirect('test_assignment_detail', assignment_id=assignment.id)
    
    try:
        result.mark_verified(request.user)
        messages.success(request, "Result verified successfully.")
        
    except ValidationError as e:
        messages.error(request, str(e))
    
    return redirect('test_assignment_detail', assignment_id=assignment.id)


@login_required
@require_POST
def release_result(request, assignment_id):
    """Release verified result to patient/doctor"""
    assignment = get_object_or_404(
        TestAssignment.objects.select_related('vendor'),
        id=assignment_id,
        vendor=request.user.vendor
    )
    
    if not hasattr(assignment, "result"):
        messages.error(request, "No result found to release.")
        return redirect('test_assignment_detail', assignment_id=assignment.id)
    
    result = assignment.result
    
    try:
        result.release_result(request.user)
        messages.success(request, "Result released successfully.")
        
    except ValidationError as e:
        messages.error(request, str(e))
    
    return redirect('test_assignment_detail', assignment_id=assignment.id)


@login_required
def instrument_status_check(request, instrument_id):
    """Check instrument connection status (AJAX endpoint)"""
    instrument = get_object_or_404(
        Equipment,
        id=instrument_id,
        vendor=request.user.vendor
    )
    
    service = InstrumentService(instrument)
    status = service.check_instrument_status()
    
    return JsonResponse(status)


@login_required
def pending_results_dashboard(request):
    """Dashboard showing all pending test assignments"""
    vendor = request.user.vendor
    
    pending_assignments = TestAssignment.objects.filter(
        vendor=vendor,
        status__in=['P', 'Q', 'I']
    ).select_related(
        'lab_test',
        'request__patient',
        'instrument',
        'assigned_to'
    ).order_by('-created_at')
    
    # Group by status
    by_status = {
        'pending': pending_assignments.filter(status='P'),
        'queued': pending_assignments.filter(status='Q'),
        'in_progress': pending_assignments.filter(status='I'),
    }
    
    # Get results awaiting verification
    awaiting_verification = TestAssignment.objects.filter(
        vendor=vendor,
        status='A'
    ).select_related('lab_test', 'request__patient')
    
    context = {
        'by_status': by_status,
        'awaiting_verification': awaiting_verification,
        'total_pending': pending_assignments.count(),
    }
    
    return render(request, 'laboratory/pending_results_dashboard.html', context)

@login_required
@require_POST
def bulk_send_to_instrument(request):
    """
    Bulk send multiple assignments to their respective instruments.
    """
    assignment_ids = request.POST.getlist('assignment_ids[]')
    
    if not assignment_ids:
        messages.error(request, "No assignments selected.")
        return redirect('laboratory:test_assignment_list')
    
    vendor = request.user.vendor
    
    # Get valid assignments
    assignments = TestAssignment.objects.filter(
        id__in=assignment_ids,
        vendor=vendor,
        status='P',
        instrument__isnull=False,
        instrument__status='active'
    ).select_related('instrument')
    
    success_count = 0
    failed_count = 0
    errors = []
    
    for assignment in assignments:
        try:
            send_assignment_to_instrument(assignment.id)
            success_count += 1
        except InstrumentAPIError as e:
            failed_count += 1
            errors.append(f"Assignment {assignment.id}: {str(e)}")
    
    # Show results
    if success_count > 0:
        messages.success(request, f"Successfully sent {success_count} assignment(s) to instruments.")
    
    if failed_count > 0:
        error_msg = f"Failed to send {failed_count} assignment(s)."
        if errors:
            error_msg += " Errors: " + "; ".join(errors[:3])  # Show first 3 errors
        messages.error(request, error_msg)
    
    return redirect('laboratory:test_assignment_list')


@login_required
@require_POST
def bulk_assign_instrument(request):
    """
    Bulk assign instrument to multiple assignments
    """
    assignment_ids = request.POST.getlist('assignment_ids[]')
    instrument_id = request.POST.get('instrument_id')
    
    if not assignment_ids:
        messages.error(request, "No assignments selected.")
        return redirect('labs:test_assignment_list')
    
    if not instrument_id:
        messages.error(request, "Please select an instrument.")
        return redirect('labs:test_assignment_list')
    
    try:
        instrument = get_object_or_404(
            Equipment,
            id=instrument_id,
            vendor=request.user.vendor,
            status='active'
        )
        
        with transaction.atomic():
            # Get assignments
            assignments = TestAssignment.objects.filter(
                id__in=assignment_ids,
                vendor=request.user.vendor,
                status__in=['P', 'I']  # Only pending or in-progress
            )
            
            updated_count = 0
            for assignment in assignments:
                assignment.instrument = instrument
                assignment.save(update_fields=['instrument'])
                updated_count += 1
            
            # Create audit log
            AuditLog.objects.create(
                vendor=request.user.vendor,
                user=request.user,
                action=f"Bulk assigned {updated_count} assignments to {instrument.name}",
                ip_address=request.META.get('REMOTE_ADDR')
            )
            
            messages.success(
                request,
                f"Successfully assigned {updated_count} test(s) to {instrument.name}."
            )
            
    except Exception as e:
        logger.error(f"Bulk assignment error: {e}", exc_info=True)
        messages.error(request, f"Error: {str(e)}")
    
    return redirect('labs:test_assignment_list')


@login_required
@require_POST
def auto_assign_instruments(request):
    """
    Automatically assign instruments to pending assignments based on:
    1. Test department
    2. Instrument availability
    3. API configuration (prefer API-enabled)
    """
    vendor = request.user.vendor
    
    # Get all pending assignments without instruments
    pending_assignments = TestAssignment.objects.filter(
        vendor=vendor,
        status='P',
        instrument__isnull=True
    ).select_related('lab_test', 'department')
    
    if not pending_assignments.exists():
        messages.info(request, "No pending assignments need instrument assignment.")
        return redirect('labs:test_assignment_list')
    
    assigned_count = 0
    failed_count = 0
    
    with transaction.atomic():
        for assignment in pending_assignments:
            # Try to find suitable instrument
            # Priority 1: Same department, active, has API endpoint
            suitable_instrument = Equipment.objects.filter(
                vendor=vendor,
                department=assignment.department,
                status='active'
            ).exclude(api_endpoint='').first()
            
            if not suitable_instrument:
                # Priority 2: Same department, active (no API required)
                suitable_instrument = Equipment.objects.filter(
                    vendor=vendor,
                    department=assignment.department,
                    status='active'
                ).first()
            
            if suitable_instrument:
                assignment.instrument = suitable_instrument
                assignment.save(update_fields=['instrument'])
                assigned_count += 1
            else:
                failed_count += 1
        
        # Create audit log
        if assigned_count > 0:
            AuditLog.objects.create(
                vendor=vendor,
                user=request.user,
                action=f"Auto-assigned instruments to {assigned_count} assignments (Smart routing)",
                ip_address=request.META.get('REMOTE_ADDR')
            )
    
    if assigned_count > 0:
        messages.success(
            request,
            f"✅ Successfully auto-assigned {assigned_count} test(s) to instruments."
        )
    
    if failed_count > 0:
        messages.warning(
            request,
            f"⚠️ {failed_count} test(s) could not be assigned. "
            f"No suitable instruments found in their departments."
        )
    
    return redirect('labs:test_assignment_list')

@login_required
@require_POST
def bulk_assign_technician(request):
    """
    Bulk assign technician to multiple assignments.
    """
    from django.contrib.auth import get_user_model
    User = get_user_model()
    
    assignment_ids = request.POST.getlist('assignment_ids[]')
    user_id = request.POST.get('user_id')
    
    if not assignment_ids or not user_id:
        messages.error(request, "Please select assignments and a technician.")
        return redirect('laboratory:test_assignment_list')
    
    vendor = request.user.vendor
    
    # Validate user
    user = get_object_or_404(User, id=user_id, vendor=vendor)
    
    # Update assignments
    updated = TestAssignment.objects.filter(
        id__in=assignment_ids,
        vendor=vendor,
        status__in=['P', 'Q', 'I']
    ).update(assigned_to=user)
    
    messages.success(request, f"Assigned {updated} test(s) to {user.get_full_name()}.")
    return redirect('labs:test_assignment_list')

# # send_to_instrument - AJAX version 
# @login_required
# @require_POST
# def quick_send_to_instrument(request, assignment_id):
#     """
#     Quick action: Send single assignment to instrument from list view.
#     This is for AJAX calls from the list page.
#     """
#     assignment = get_object_or_404(
#         TestAssignment,
#         id=assignment_id,
#         vendor=request.user.vendor
#     )
    
#     if not assignment.can_send_to_instrument():
#         return JsonResponse({
#             'success': False,
#             'error': 'Cannot send to instrument. Check status and instrument assignment.'
#         }, status=400)
    
#     try:
#         result = send_assignment_to_instrument(assignment_id)
        
#         return JsonResponse({
#             'success': True,
#             'message': f'Sent to {assignment.instrument.name}',
#             'external_id': result.get('id'),
#             'new_status': 'Q',
#             'new_status_display': 'Queued'
#         })
        
#     except InstrumentAPIError as e:
#         return JsonResponse({
#             'success': False,
#             'error': str(e)
#         }, status=500)


@login_required
def export_assignments_csv(request):
    """
    Export filtered assignments to CSV.
    """
    import csv
    from django.http import HttpResponse
    from django.utils import timezone
    
    vendor = request.user.vendor
    
    # Get filtered assignments (reuse filter logic)
    assignments = TestAssignment.objects.filter(vendor=vendor).select_related(
        'lab_test', 'request__patient', 'instrument', 'department'
    )
    
    # Apply same filters as list view
    status_filter = request.GET.get('status', '')
    if status_filter:
        assignments = assignments.filter(status=status_filter)
    
    # Create CSV response
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="assignments_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'
    
    writer = csv.writer(response)
    writer.writerow([
        'Assignment ID',
        'Request ID',
        'Patient',
        'Test',
        'Sample',
        'Department',
        'Instrument',
        'Status',
        'Priority',
        'Created',
        'Queued',
        'Analyzed',
        'Verified'
    ])
    
    for assignment in assignments:
        writer.writerow([
            assignment.id,
            assignment.request.request_id,
            str(assignment.request.patient),
            assignment.lab_test.name,
            assignment.sample.sample_id,
            assignment.department.name,
            assignment.instrument.name if assignment.instrument else 'Not Assigned',
            assignment.get_status_display(),
            assignment.request.priority,
            assignment.created_at.strftime('%Y-%m-%d %H:%M'),
            assignment.queued_at.strftime('%Y-%m-%d %H:%M') if assignment.queued_at else '',
            assignment.analyzed_at.strftime('%Y-%m-%d %H:%M') if assignment.analyzed_at else '',
            assignment.verified_at.strftime('%Y-%m-%d %H:%M') if assignment.verified_at else '',
        ])
    
    return response


@login_required
def assignment_quick_stats(request):
    """
    AJAX endpoint for real-time stats updates.
    """
    vendor = request.user.vendor
    
    stats = TestAssignment.objects.filter(vendor=vendor).aggregate(
        total=Count('id'),
        pending=Count('id', filter=Q(status='P')),
        queued=Count('id', filter=Q(status='Q')),
        in_progress=Count('id', filter=Q(status='I')),
        completed=Count('id', filter=Q(status='A')),
        verified=Count('id', filter=Q(status='V')),
    )
    
    return JsonResponse(stats)



# @login_required
# def instrument_logs_list(request, assignment_id):
#     """View all instrument communication logs for an assignment"""
#     assignment = get_object_or_404(
#         TestAssignment.objects.select_related('instrument'),
#         id=assignment_id,
#         vendor=request.user.vendor
#     )
    
#     logs = assignment.instrument_logs.all().select_related('instrument')
    
#     context = {
#         'assignment': assignment,
#         'logs': logs,
#     }
    
#     return render(request, 'laboratory/assignment/instrument_logs_list.html', context)



"""
QUALITY CONTROL...
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.utils import timezone
from datetime import datetime, timedelta
from .forms import QCLotForm, QCActionForm, QCEntryForm
from .models import QCLot, QCAction, QCResult, QCTestApproval
import calendar
from django.db.models import Count, Q

# ==========================================
# QC LOT MANAGEMENT
# ==========================================

@login_required
def qc_lot_list(request):
    """List all QC lots."""
    vendor = request.user.vendor
    
    lots = QCLot.objects.filter(
        vendor=vendor
    ).select_related('test').order_by('-is_active', '-received_date')
    
    # Filter
    test_filter = request.GET.get('test')
    if test_filter:
        lots = lots.filter(test_id=test_filter)
    
    active_filter = request.GET.get('active')
    if active_filter == 'true':
        lots = lots.filter(is_active=True)
    
    tests = VendorTest.objects.filter(vendor=vendor)
    
    context = {
        'lots': lots,
        'tests': tests,
        'current_test': test_filter,
    }
    
    return render(request, 'laboratory/qc/lots/qclot_list.html', context)


@login_required
def qc_lot_create(request):
    """Create new QC lot."""
    vendor = request.user.vendor
    
    if request.method == 'POST':
        form = QCLotForm(request.POST, vendor=vendor)
        if form.is_valid():
            qc_lot = form.save(commit=False)
            qc_lot.vendor = vendor
            qc_lot.save()
            messages.success(request, f"QC Lot {qc_lot.lot_number} created successfully.")
            return redirect('labs:qclot_list')
    else:
        form = QCLotForm(vendor=vendor)
    
    return render(request, 'laboratory/qc/lots/qclot_form.html', {'form': form})


@login_required
def qc_lot_edit(request, pk):
    vendor = request.user.vendor
    qc_lot = get_object_or_404(QCLot, pk=pk, vendor=vendor)
    if request.method == 'POST':
        form = QCLotForm(vendor, request.POST, instance=qc_lot)
        if form.is_valid():
            form.save()
            messages.success(request, f'QC Lot {qc_lot} updated')
            return redirect('qc:qclot_list')
    else:
        form = QCLotForm(vendor, instance=qc_lot)
    return render(request, 'laboratory/qc/qclot_form.html', {'form': form, 'create': False, 'qclot': qc_lot})


@login_required
def qclot_toggle_active(request, pk):
    vendor = request.user.vendor
    q = get_object_or_404(QCLot, pk=pk, vendor=vendor)

    if q.is_active:
        # Deactivating
        q.is_active = False
        q.closed_date = timezone.now().date()
        q.save()
        messages.info(request, f'{q} deactivated')
    else:
        # Activating: will automatically deactivate others in model.save()
        if q.expiry_date and q.expiry_date < timezone.now().date():
            messages.error(request, 'Cannot activate an expired lot')
        else:
            q.is_active = True
            q.save()
            messages.success(request, f'{q} activated (others deactivated)')

    return redirect('labs:qclot_list')


@login_required
def qclot_delete(request, pk):
    vendor = request.user.vendor
    q = get_object_or_404(QCLot, pk=pk, vendor=vendor)
    if request.method == 'POST':
        q.delete()
        messages.success(request, 'QC Lot deleted')
        return redirect('qc:qclot_list')
    return render(request, 'laboratory/qc/qclot_confirm_delete.html', {'qclot': q})


@login_required
def qc_entry_view(request):
    vendor = request.user.vendor
    today = timezone.now().date()

    if request.method == "POST":
        form = QCEntryForm(vendor, request.POST)
        if form.is_valid():
            qc = form.save(commit=False)
            qc.vendor = vendor
            qc.entered_by = request.user

            qc.run_date = today
            qc.run_number = (
                QCResult.objects.filter(
                    vendor=vendor,
                    qc_lot=qc.qc_lot,
                    run_date=today
                ).count() + 1
            )

            qc.save()
            messages.success(request, f"QC saved — Status: {qc.status}")
            return redirect("qc_entry")
    else:
        form = QCEntryForm(vendor)

    todays_runs = QCResult.objects.filter(
        vendor=vendor,
        run_date=today
    ).select_related("qc_lot", "instrument")

    total_runs = todays_runs.count()
    passed_runs = todays_runs.filter(status="PASS").count()
    runs_with_violations = todays_runs.exclude(rule_violations=[]).count()

    context = {
        "form": form,
        "todays_runs": todays_runs,
        "total_runs": total_runs,
        "passed_runs": passed_runs,
        "runs_with_violations": runs_with_violations,
        "daily_approval_rate": round((passed_runs / total_runs * 100), 2) if total_runs else 0,
        "active_lots": QCLot.objects.filter(vendor=vendor, is_active=True).count(),
        "today": today,
    }

    return render(request, "laboratory/qc/entry/qc_entry.html", context)

# ==========================================
# LEVEY-JENNINGS CHART - Data Endpoint
# ==========================================

@login_required
def levey_jennings_data(request, qc_lot_id):
    """
    API endpoint to get data for Levey-Jennings chart.
    Returns JSON data for Chart.js.
    """
    vendor = request.user.vendor
    qc_lot = get_object_or_404(QCLot, id=qc_lot_id, vendor=vendor)
    
    # Get date range (default: last 30 days)
    days = int(request.GET.get('days', 30))
    start_date = timezone.now().date() - timedelta(days=days)
    
    # Get QC results
    results = QCResult.objects.filter(
        qc_lot=qc_lot,
        run_date__gte=start_date
    ).order_by('run_date', 'run_time')
    
    # Build chart data
    labels = []
    data_points = []
    colors = []
    
    for result in results:
        labels.append(result.run_date.strftime('%m/%d'))
        data_points.append(float(result.result_value))
        
        # Color based on status
        if result.status == 'PASS':
            colors.append('rgba(75, 192, 192, 1)')  # Green
        elif result.status == 'WARNING':
            colors.append('rgba(255, 206, 86, 1)')  # Yellow
        else:
            colors.append('rgba(255, 99, 132, 1)')  # Red
    
    # Control limits
    chart_data = {
        'labels': labels,
        'datasets': [
            {
                'label': 'QC Results',
                'data': data_points,
                'borderColor': 'rgba(54, 162, 235, 1)',
                'backgroundColor': colors,
                'pointBackgroundColor': colors,
                'pointBorderColor': colors,
                'pointRadius': 5,
                'fill': False,
            }
        ],
        'control_limits': {
            'mean': float(qc_lot.mean),
            'sd_2_high': float(qc_lot.limit_2sd_high),
            'sd_2_low': float(qc_lot.limit_2sd_low),
            'sd_3_high': float(qc_lot.limit_3sd_high),
            'sd_3_low': float(qc_lot.limit_3sd_low),
        },
        'lot_info': {
            'test': qc_lot.test.name,
            'level': qc_lot.get_level_display(),
            'lot_number': qc_lot.lot_number,
            'target': float(qc_lot.target_value),
            'units': qc_lot.units,
        }
    }
    
    return JsonResponse(chart_data)

# ==========================================
# LEVEY-JENNINGS CHART - View
# ==========================================

@login_required
def levey_jennings_chart(request, qc_lot_id=None):
    """
    Display Levey-Jennings chart for a QC lot.
    """
    vendor = request.user.vendor
    
    # Get all active QC lots for selection
    active_lots = QCLot.objects.filter(
        vendor=vendor,
        is_active=True
    ).select_related('test').order_by('test__name', 'level')
    
    qc_lot = None
    if qc_lot_id:
        qc_lot = get_object_or_404(QCLot, id=qc_lot_id, vendor=vendor)
    elif active_lots.exists():
        qc_lot = active_lots.first()
    
    context = {
        'qc_lot': qc_lot,
        'active_lots': active_lots,
    }
    return render(request, 'laboratory/qc/levey/levey_jennings.html', context)


@login_required
def qc_results_list(request):
    vendor = request.user.vendor

    results = QCResult.objects.filter(
        vendor=vendor
    ).select_related("qc_lot", "qc_lot__test", "instrument", "entered_by", "approved_by")

    # Summary stats
    total_runs = results.count()
    passed = results.filter(status='PASS').count()
    failed = results.filter(status='FAIL').count()
    warnings = results.filter(status='WARNING').count()
    approved = results.filter(is_approved=True).count()
    violations = results.filter(rule_violations__len__gt=0).count()  # if rule_violations is list-like

    # Optional: compute per-test metrics
    tests_summary = {}
    for r in results:
        if hasattr(r, 'z_score') and r.z_score is not None:
            r.z_score_abs = abs(r.z_score)
        else:
            r.z_score_abs = None

        test_code = r.qc_lot.test.code
        if test_code not in tests_summary:
            tests_summary[test_code] = {
                "test": r.qc_lot.test,
                "total": 0,
                "passed": 0,
                "failed": 0,
                "warnings": 0,
            }
        tests_summary[test_code]["total"] += 1
        if r.status == "PASS":
            tests_summary[test_code]["passed"] += 1
        elif r.status == "FAIL":
            tests_summary[test_code]["failed"] += 1
        else:
            tests_summary[test_code]["warnings"] += 1

    # Final per-test computation
    for item in tests_summary.values():
        t = item["total"]
        item["pass_rate"] = (item["passed"] / t * 100) if t else 0
        item["fail_rate"] = (item["failed"] / t * 100) if t else 0
        item["warning_rate"] = (item["warnings"] / t * 100) if t else 0

    context = {
        "results": results,
        "total_runs": total_runs,
        "passed": passed,
        "failed": failed,
        "warnings": warnings,
        "approved": approved,
        "violations": violations,
        "tests_summary": tests_summary,
    }

    return render(request, "laboratory/qc/entry/qc_results_list.html", context)


@login_required
def qc_result_detail(request, pk):
    vendor = request.user.vendor

    result = get_object_or_404(
        QCResult.objects.select_related(
            "qc_lot", "qc_lot__test", "instrument", "entered_by"
        ),
        pk=pk,
        vendor=vendor
    )

    context = {"result": result}
    return render(request, "laboratory/qc/entry/qc_result_detail.html", context)


# ==========================================
# QC REPORTS
# ==========================================

@login_required
def qc_monthly_report(request):
    """Monthly QC summary report."""
    vendor = request.user.vendor
    
    # Get month and year from request
    year = int(request.GET.get('year', timezone.now().year))
    month = int(request.GET.get('month', timezone.now().month))
    
    # Month dropdown list
    months = [
        {"num": m, "name": calendar.month_name[m]}
        for m in range(1, 13)
    ]

    # Year dropdown list (current year ± 2)
    current_year = timezone.now().year
    years = list(range(current_year - 2, current_year + 1))

    # Calculate date range
    start_date = datetime(year, month, 1).date()
    if month == 12:
        end_date = datetime(year + 1, 1, 1).date() - timedelta(days=1)
    else:
        end_date = datetime(year, month + 1, 1).date() - timedelta(days=1)
    
    # Query QC results
    results = QCResult.objects.filter(
        vendor=vendor,
        run_date__gte=start_date,
        run_date__lte=end_date
    ).select_related('qc_lot__test')
    
    total_runs = results.count()
    passed = results.filter(status='PASS').count()
    failed = results.filter(status='FAIL').count()
    warnings = results.filter(status='WARNING').count()

    # Compute overall rates
    pass_rate = (passed / total_runs * 100) if total_runs else 0
    warning_rate = (warnings / total_runs * 100) if total_runs else 0
    fail_rate = (failed / total_runs * 100) if total_runs else 0

    # Group by test + compute test-level percentages
    tests_summary = {}
    
    for result in results:
        test = result.qc_lot.test
        code = test.code
        
        if code not in tests_summary:
            tests_summary[code] = {
                "test": test,
                "total": 0,
                "passed": 0,
                "failed": 0,
                "warnings": 0,
                "pass_rate": 0,
                "warning_rate": 0,
                "fail_rate": 0,
            }
        
        tests_summary[code]["total"] += 1
        
        if result.status == "PASS":
            tests_summary[code]["passed"] += 1
        elif result.status == "FAIL":
            tests_summary[code]["failed"] += 1
        else:
            tests_summary[code]["warnings"] += 1

    # Final computation for each test + sigma conversion
    for item in tests_summary.values():
        t = item["total"]

        if t > 0:
            item["pass_rate"] = item["passed"] / t * 100
            item["warning_rate"] = item["warnings"] / t * 100
            item["fail_rate"] = item["failed"] / t * 100
            # Sigma approximation: pass rate expressed on sigma scale (0–6)
            item["sigma"] = round((item["pass_rate"] / 100) * 6, 2)
        else:
            item["pass_rate"] = 0
            item["warning_rate"] = 0
            item["fail_rate"] = 0
            item["sigma"] = 0

    overall_sigma = round((pass_rate / 100) * 6, 2)

    context = {
        "year": year,
        "month": month,
        "years": years,
        "months": months,
        "month_name": datetime(year, month, 1).strftime("%B %Y"),

        "start_date": start_date,
        "end_date": end_date,

        "total_runs": total_runs,
        "passed": passed,
        "failed": failed,
        "warnings": warnings,

        "pass_rate": round(pass_rate, 1),
        "warning_rate": round(warning_rate, 1),
        "fail_rate": round(fail_rate, 1),
        "overall_sigma": overall_sigma,
        "tests_summary": tests_summary,
    }
    
    return render(request, "laboratory/qc/metric/monthly_report.html", context)


# ==========================================
# QC DASHBOARD - Overview of QC Status
# ==========================================

@login_required
def qc_dashboard(request):
    """
    Main QC dashboard showing today's QC status for all tests.
    """
    vendor = request.user.vendor
    today = timezone.now().date()
    
    # Get all active QC lots
    active_lots = QCLot.objects.filter(
        vendor=vendor,
        is_active=True,
        expiry_date__gte=today
    ).select_related('test').order_by('test__name', 'level')
    
    # Get today's QC results
    todays_results = QCResult.objects.filter(
        vendor=vendor,
        run_date=today
    ).select_related('qc_lot', 'qc_lot__test', 'instrument')
    
    # Get test approvals for today
    test_approvals = QCTestApproval.objects.filter(
        vendor=vendor,
        date=today
    ).select_related('test')
    
    # Build summary by test
    qc_summary = {}
    for lot in active_lots:
        test_code = lot.test.code
        if test_code not in qc_summary:
            qc_summary[test_code] = {
                'test': lot.test,
                'levels': {},
                'all_passed': True,
                'any_run': False
            }
        
        # Check if this level was run today
        level_result = todays_results.filter(qc_lot=lot).first()
        qc_summary[test_code]['levels'][lot.get_level_display()] = {
            'lot': lot,
            'result': level_result,
            'status': level_result.status if level_result else 'NOT_RUN'
        }
        
        if level_result:
            qc_summary[test_code]['any_run'] = True
            if level_result.status != 'PASS':
                qc_summary[test_code]['all_passed'] = False
        else:
            qc_summary[test_code]['all_passed'] = False
    
    # Statistics
    stats = {
        'total_tests': len(qc_summary),
        'tests_approved': sum(1 for t in qc_summary.values() if t['all_passed']),
        'tests_failed': sum(1 for t in qc_summary.values() if t['any_run'] and not t['all_passed']),
        'tests_pending': sum(1 for t in qc_summary.values() if not t['any_run']),
        'total_runs_today': todays_results.count(),
    }
    
    # Recent failures (last 7 days)
    recent_failures = QCResult.objects.filter(
        vendor=vendor,
        run_date__gte=today - timedelta(days=7),
        status='FAIL'
    ).select_related('qc_lot__test')[:10]
    
    context = {
        'qc_summary': qc_summary,
        'stats': stats,
        'recent_failures': recent_failures,
        'today': today,
    }
    
    return render(request, 'laboratory/qc/qc_dashboard.html', context)


# ==========================================
# QC ACTIONS
# ==========================================

@login_required
def qc_action_create(request, result_pk):
    """
    Create corrective action for a failed QC result.
    """
    vendor = request.user.vendor
    qc_result = get_object_or_404(QCResult, pk=result_pk, vendor=vendor)
    
    # Only allow actions for failed/warning QC
    if qc_result.status == 'PASS':
        messages.warning(request, "Cannot create action for passing QC.")
        return redirect('labs:qc_result_detail', pk=result_pk)
    
    if request.method == 'POST':
        form = QCActionForm(request.POST)
        if form.is_valid():
            action = form.save(commit=False)
            action.qc_result = qc_result
            action.performed_by = request.user
            action.save()
            
            # Update QC result with corrective action taken
            if not qc_result.corrective_action:
                qc_result.corrective_action = action.description
                qc_result.save(update_fields=['corrective_action'])
            
            messages.success(request, f"Corrective action '{action.get_action_type_display()}' recorded.")
            return redirect('labs:qc_result_detail', pk=result_pk)
    else:
        form = QCActionForm()
    
    context = {
        'form': form,
        'qc_result': qc_result,
    }
    return render(request, 'laboratory/qc/actions/qc_action_form.html', context)


@login_required
def qc_action_list(request):
    """
    List all corrective actions with filtering.
    """
    vendor = request.user.vendor
    
    actions = QCAction.objects.filter(
        qc_result__vendor=vendor
    ).select_related(
        'qc_result__qc_lot__test',
        'performed_by'
    ).order_by('-performed_at')
    
    # Filters
    resolved_filter = request.GET.get('resolved')
    if resolved_filter == 'true':
        actions = actions.filter(resolved=True)
    elif resolved_filter == 'false':
        actions = actions.filter(resolved=False)
    
    action_type_filter = request.GET.get('action_type')
    if action_type_filter:
        actions = actions.filter(action_type=action_type_filter)
    
    # Statistics
    stats = {
        'total': actions.count(),
        'resolved': actions.filter(resolved=True).count(),
        'pending': actions.filter(resolved=False).count(),
    }
    
    # Action type choices for filter dropdown
    action_types = QCAction.ACTION_TYPE_CHOICES
    
    context = {
        'actions': actions,
        'stats': stats,
        'action_types': action_types,
    }
    return render(request, 'laboratory/qc/actions/qc_action_list.html', context)


@login_required
def qc_action_detail(request, pk):
    """
    View and update a single corrective action.
    """
    vendor = request.user.vendor
    action = get_object_or_404(
        QCAction.objects.select_related('qc_result__qc_lot__test', 'performed_by'),
        pk=pk,
        qc_result__vendor=vendor
    )
    
    if request.method == 'POST':
        form = QCActionForm(request.POST, instance=action)
        if form.is_valid():
            form.save()
            messages.success(request, "Action updated successfully.")
            return redirect('labs:qc_action_detail', pk=pk)
    else:
        form = QCActionForm(instance=action)
    
    # Get follow-up QC results after this action
    follow_up_results = QCResult.objects.filter(
        vendor=vendor,
        qc_lot=action.qc_result.qc_lot,
        run_date__gte=action.performed_at.date()
    ).order_by('run_date', 'run_time')[:5]
    
    context = {
        'action': action,
        'form': form,
        'follow_up_results': follow_up_results,
    }
    return render(request, 'laboratory/qc/actions/qc_action_detail.html', context)