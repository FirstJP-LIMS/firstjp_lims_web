from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from functools import wraps
from .utils import check_tenant_access
from django.contrib import messages
from django.db import transaction
from django.urls import reverse_lazy
from .forms import (
    DepartmentForm,
    # PatientForm, 
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
    AuditLog
)
from django.core.paginator import Paginator

from django.urls import reverse
from django.contrib.auth.decorators import login_required
from apps.tenants.models import Vendor

from django.shortcuts import render, get_object_or_404
from django.db.models import Sum
from django.contrib.auth.decorators import login_required
from apps.accounts.models import VendorProfile
from django.core.paginator import Paginator
import logging


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

from datetime import timedelta
from django.utils import timezone

# --- CRM Views ---
# # dashboard 
# @login_required
# @tenant_required
# def dashboard(request):
#     tenant = request.tenant
#     is_platform_admin = request.is_platform_admin
#     if is_platform_admin and not tenant:
#         return render(request, "laboratory/registration/login.html")

#     # Fetch lab Departments to the header
#     try:
#         lab_departments = tenant.departments.all().order_by('name')
#     except AttributeError:
#         lab_departments = []

#     lab_name = getattr(tenant, 'business_name', tenant.name)

#     # filter time from query params
#     date_filter = request.GET.get("filter", "7days")

#     # Fetch recent samples for this vendor
#     samples_qs = Sample.objects.filter(vendor=tenant).select_related('test_request__patient').prefetch_related('test_request__requested_tests')

#     # 🧮 Apply time filtering
#     now = timezone.now()
#     if date_filter == "today":
#         samples_qs = samples_qs.filter(collected_at__date=now.date())
#     elif date_filter == "7days":
#         samples_qs = samples_qs.filter(collected_at__gte=now - timedelta(days=7))
#     elif date_filter == "30days":
#         samples_qs = samples_qs.filter(collected_at__gte=now - timedelta(days=30))

#     # Sort newest first
#     samples_qs = samples_qs.order_by('-collected_at')

#     # Pagination
#     paginator = Paginator(samples_qs, 10)  # 10 samples per page
#     page_number = request.GET.get("page")
#     samples_page = paginator.get_page(page_number)

#     context = {
#         "vendor": tenant,
#         "lab_name": lab_name,
#         "vendor_domain": tenant.domains.first().domain_name if tenant.domains.exists() else None,
#         "lab_departments": lab_departments,
#         "samples": samples_page,  # Pagination added
#         "current_filter": date_filter,
#     }
#     return render(request, "laboratory/dashboard.html", context)




from datetime import timedelta
from django.utils import timezone
from django.core.paginator import Paginator
from django.db.models import Count, F, Q, Avg, ExpressionWrapper, DurationField
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

# Assuming tenant_required, Sample, TestAssignment, and other models are imported correctly
# from .decorators import tenant_required
# from .models import Sample, TestAssignment, TestResult, ... 

# NOTE: The full function signature with necessary imports/decorators is assumed 
# to exist in your environment.

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
        
    # --- 3. Pagination for Recent Samples ---
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


# # ***********************
# Test Requests / C Operation
# Models involved are: Sample, TestRequest, TestAssignment
# ***********************
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


# update 
# update 
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


from django.contrib.auth.decorators import user_passes_test

def is_lab_staff_or_admin(user):
    return user.role in ["vendor_admin", "lab_staff"]


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
# Download TestRequest
# *******************
from django.template.loader import render_to_string
from io import BytesIO
from xhtml2pdf import pisa
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
from django.db.models import Sum
from .models import TestRequest

from .utils import generate_barcode_base64

def render_to_pdf(html_content):
    """Utility to convert rendered HTML to PDF."""
    result = BytesIO()
    pdf = pisa.pisaDocument(BytesIO(html_content.encode("UTF-8")), result)
    return result.getvalue() if not pdf.err else None

@login_required
def download_test_request(request, pk=None, blank=False):
    """Download a filled or blank Test Request form as PDF."""
    vendor = getattr(request.user, "vendor", None)
    vendor_profile = getattr(vendor, "profile", None)

    # Handle missing logo gracefully
    if vendor_profile and not vendor_profile.logo:
        vendor_profile.logo = None

    if blank:
        # Blank form version — for physical clients
        context = {
            "vendor": vendor,
            "vendor_profile": vendor_profile,
            "blank": True,
        }
        filename = f"Blank_Test_Request_{vendor.name}.pdf"
    else:
        # Filled form version — for completed requests
        test_request = get_object_or_404(TestRequest, pk=pk, vendor=vendor)

        requested_tests = test_request.requested_tests.select_related("assigned_department")
        samples = test_request.samples.all()
        total_cost = requested_tests.aggregate(total=Sum("price"))["total"] or 0.00
        payment_mode = getattr(test_request, "payment_mode", "Not Specified")

        # ✅ Generate barcode (based on request ID or any unique field)
        barcode_image = generate_barcode_base64(test_request.request_id)

        context = {
            "vendor": vendor,
            "vendor_profile": vendor_profile,
            "test_request": test_request,
            "requested_tests": requested_tests,
            "samples": samples,
            "total_cost": total_cost,
            "payment_mode": payment_mode,
            "barcode_image": barcode_image,  # <--- added barcode here
            "blank": False,
        }
        filename = f"TestRequest_{test_request.request_id}.pdf"

    html = render_to_string("laboratory/requests/pdf_template.html", context)
    pdf_file = render_to_pdf(html)

    response = HttpResponse(pdf_file, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response

# **************************************************
# Post Examination Section
# ---- Post test, get result, and prepare result 
    # TestAssignment → represents a job sent to the instrument.
    # TestResult → holds result data.
    # VendorTest → defines reference range (min/max).
# ***************************************************

from django.shortcuts import get_object_or_404, render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_http_methods
from django.db import transaction
from django.http import JsonResponse
from django.core.exceptions import ValidationError

from .models import TestAssignment, TestResult, Equipment, AuditLog
from .services import (
    InstrumentService, 
    InstrumentAPIError,
    send_assignment_to_instrument,
    fetch_assignment_result
)


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
    """Manually enter test result"""
    assignment = get_object_or_404(
        TestAssignment.objects.select_related('lab_test', 'vendor', 'request__patient'),
        id=assignment_id,
        vendor=request.user.vendor
    )
    
    # Check if assignment is in correct status
    if assignment.status not in ['P', 'Q', 'I']:
        messages.error(request, "Cannot enter result for this assignment in current status.")
        return redirect('test_assignment_detail', assignment_id=assignment.id)
    
    # Check if result already exists and is verified
    if hasattr(assignment, 'result') and assignment.result.verified_at:
        messages.error(request, "Cannot modify verified result.")
        return redirect('test_assignment_detail', assignment_id=assignment.id)
    
    if request.method == "POST":
        value = request.POST.get("result_value", "").strip()
        unit = request.POST.get("unit", "").strip()
        remarks = request.POST.get("remarks", "").strip()
        
        # Validate required fields
        if not value:
            messages.error(request, "Result value is required.")
            return render(request, "laboratory/manual_result_form.html", {
                "assignment": assignment
            })
        
        try:
            with transaction.atomic():
                # Get or create result
                result, created = TestResult.objects.get_or_create(
                    assignment=assignment,
                    defaults={
                        'data_source': 'manual',
                        'entered_by': request.user,
                    }
                )
                
                # If updating existing result, track the change
                if not created and result.result_value != value:
                    result.update_result(value, request.user, reason="Manual correction")
                else:
                    result.result_value = value
                
                result.units = unit or assignment.lab_test.default_units or ''
                result.remarks = remarks
                
                # Set reference range
                if assignment.lab_test.min_reference_value and assignment.lab_test.max_reference_value:
                    result.reference_range = (
                        f"{assignment.lab_test.min_reference_value} - "
                        f"{assignment.lab_test.max_reference_value}"
                    )
                elif assignment.lab_test.default_reference_text:
                    result.reference_range = assignment.lab_test.default_reference_text
                
                result.save()
                
                # Auto-flag the result
                result.auto_flag_result()
                
                # Update assignment status
                assignment.mark_analyzed()
                
                # Log the action
                AuditLog.objects.create(
                    vendor=assignment.vendor,
                    user=request.user,
                    action=f"Manual result entered for {assignment.request.request_id} - {assignment.lab_test.code}",
                    ip_address=request.META.get('REMOTE_ADDR')
                )
                
                messages.success(request, "Manual result entered successfully.")
                return redirect('test_assignment_detail', assignment_id=assignment.id)
                
        except Exception as e:
            messages.error(request, f"Error saving result: {str(e)}")
            logger.error(f"Error saving manual result for assignment {assignment_id}: {e}")
    
    return render(request, "laboratory/manual_result_form.html", {
        "assignment": assignment,
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


# views.py - Add to your existing views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Count, Prefetch
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from .models import TestAssignment, Equipment, TestResult, Department
from .services import send_assignment_to_instrument, InstrumentAPIError


@login_required
def test_assignment_list(request):
    """
    List all test assignments with filtering, search, and bulk actions.
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
    }
    
    # Pagination
    paginator = Paginator(assignments, 25)  # 25 items per page
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    # Get filter options for dropdowns
    departments = Department.objects.filter(vendor=vendor)
    instruments = Equipment.objects.filter(vendor=vendor, status='active')
    
    context = {
        'page_obj': page_obj,
        'assignments': page_obj.object_list,
        'stats': stats,
        'departments': departments,
        'instruments': instruments,
        
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
    Bulk assign instrument to multiple assignments.
    """
    assignment_ids = request.POST.getlist('assignment_ids[]')
    instrument_id = request.POST.get('instrument_id')
    
    if not assignment_ids or not instrument_id:
        messages.error(request, "Please select assignments and an instrument.")
        return redirect('laboratory:test_assignment_list')
    
    vendor = request.user.vendor
    
    # Validate instrument
    instrument = get_object_or_404(
        Equipment,
        id=instrument_id,
        vendor=vendor,
        status='active'
    )
    
    # Update assignments
    updated = TestAssignment.objects.filter(
        id__in=assignment_ids,
        vendor=vendor,
        status='P'  # Only pending assignments
    ).update(instrument=instrument)
    
    messages.success(request, f"Assigned {updated} test(s) to {instrument.name}.")
    return redirect('laboratory:test_assignment_list')


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


@login_required
@require_POST
def quick_send_to_instrument(request, assignment_id):
    """
    Quick action: Send single assignment to instrument from list view.
    This is for AJAX calls from the list page.
    """
    assignment = get_object_or_404(
        TestAssignment,
        id=assignment_id,
        vendor=request.user.vendor
    )
    
    if not assignment.can_send_to_instrument():
        return JsonResponse({
            'success': False,
            'error': 'Cannot send to instrument. Check status and instrument assignment.'
        }, status=400)
    
    try:
        result = send_assignment_to_instrument(assignment_id)
        
        return JsonResponse({
            'success': True,
            'message': f'Sent to {assignment.instrument.name}',
            'external_id': result.get('id'),
            'new_status': 'Q',
            'new_status_display': 'Queued'
        })
        
    except InstrumentAPIError as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


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

