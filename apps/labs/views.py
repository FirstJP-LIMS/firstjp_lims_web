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
# dashboard 
@login_required
@tenant_required
def dashboard(request):
    tenant = request.tenant
    is_platform_admin = request.is_platform_admin
    if is_platform_admin and not tenant:
        return render(request, "laboratory/registration/login.html")

    # Fetch lab Departments to the header
    try:
        lab_departments = tenant.departments.all().order_by('name')
    except AttributeError:
        lab_departments = []

    lab_name = getattr(tenant, 'business_name', tenant.name)

    # filter time from query params
    date_filter = request.GET.get("filter", "7days")

    # Fetch recent samples for this vendor
    samples_qs = Sample.objects.filter(vendor=tenant).select_related('test_request__patient').prefetch_related('test_request__requested_tests')

    # 🧮 Apply time filtering
    now = timezone.now()
    if date_filter == "today":
        samples_qs = samples_qs.filter(collected_at__date=now.date())
    elif date_filter == "7days":
        samples_qs = samples_qs.filter(collected_at__gte=now - timedelta(days=7))
    elif date_filter == "30days":
        samples_qs = samples_qs.filter(collected_at__gte=now - timedelta(days=30))

    # Sort newest first
    samples_qs = samples_qs.order_by('-collected_at')

    # Pagination
    paginator = Paginator(samples_qs, 10)  # 10 samples per page
    page_number = request.GET.get("page")
    samples_page = paginator.get_page(page_number)

    context = {
        "vendor": tenant,
        "lab_name": lab_name,
        "vendor_domain": tenant.domains.first().domain_name if tenant.domains.exists() else None,
        "lab_departments": lab_departments,
        "samples": samples_page,  # Pagination added
        "current_filter": date_filter,
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
@login_required
def test_request_update(request, pk):
    vendor = getattr(request.user, "vendor", None)
    request_instance = get_object_or_404(TestRequest, pk=pk, vendor=vendor)

    if request.method == "POST":
        form = TestRequestForm(request.POST, instance=request_instance, vendor=vendor)
        if form.is_valid():
            try:
                with transaction.atomic():
                    updated_request = form.save(commit=False)
                    updated_request.vendor = vendor
                    updated_request.save()
                    updated_request.requested_tests.set(form.cleaned_data["tests_to_order"])

                    messages.success(request, f"{updated_request.request_id} updated successfully.")
                    return redirect("test_request_list")
            except Exception as e:
                messages.error(request, f"Error updating request: {e}")
    else:
        form = TestRequestForm(instance=request_instance, vendor=vendor)

    return render(request, "laboratory/requests/form.html", {
        "form": form,
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


# Phase 2: Examination                 
@login_required
def sample_examination_list(request):
    """List all samples awaiting verification or processing."""
    samples = Sample.objects.filter(status__in=['AC', 'RJ', 'AP']).select_related('patient', 'test_request')
    return render(request, 'laboratory/examination/sample_list.html', {'samples': samples})

  
@login_required
def sample_examination_detail(request, sample_id):
    """Detail view for verifying a specific sample."""
    sample = get_object_or_404(
        Sample.objects.select_related(
            'test_request',
            'test_request__patient',
            'vendor'
        ).prefetch_related(
            'test_request__requested_tests'
        ),
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


# from django.template.loader import render_to_string
# from io import BytesIO
# from xhtml2pdf import pisa
# from django.shortcuts import render, get_object_or_404
# from django.http import HttpResponse
# from django.template.loader import render_to_string
# from django.db.models import Sum
# from django.contrib.auth.decorators import login_required

# from .models import TestRequest
# from .utils import generate_barcode_base64
# from .pdf import render_to_pdf  # Assuming you already have this helper


# utils.py
import io
import base64
import barcode
from barcode.writer import ImageWriter

def generate_barcode_base64(data):
    """
    Generate a barcode image for given data (like request_id)
    and return it as a base64-encoded string for embedding in HTML.
    """
    buffer = io.BytesIO()
    code128 = barcode.get('code128', data, writer=ImageWriter())
    code128.write(buffer, options={'module_width': 0.4, 'module_height': 10.0})
    buffer.seek(0)
    img_base64 = base64.b64encode(buffer.read()).decode('utf-8')
    return f"data:image/png;base64,{img_base64}"

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



# @login_required
# def download_test_request(request, pk=None, blank=False):
#     """Download a filled or blank Test Request form as PDF."""
#     vendor = getattr(request.user, "vendor", None)
#     vendor_profile = getattr(vendor, "profile", None)

#     # Handle missing logo gracefully
#     if vendor_profile and not vendor_profile.logo:
#         vendor_profile.logo = None

#     if blank:
#         # Blank form version — for physical clients
#         context = {
#             "vendor": vendor,
#             "vendor_profile": vendor_profile,
#             "blank": True,
#         }
#         filename = f"Blank_Test_Request_{vendor.name}.pdf"
#     else:
#         # Filled form version — for completed requests
#         test_request = get_object_or_404(TestRequest, pk=pk, vendor=vendor)

#         requested_tests = test_request.requested_tests.select_related("assigned_department")
#         samples = test_request.samples.all()
#         total_cost = requested_tests.aggregate(total=Sum("price"))["total"] or 0.00
#         payment_mode = getattr(test_request, "payment_mode", "Not Specified")

#         context = {
#             "vendor": vendor,
#             "vendor_profile": vendor_profile,
#             "test_request": test_request,
#             "requested_tests": requested_tests,
#             "samples": samples,
#             "total_cost": total_cost,
#             "payment_mode": payment_mode,
#             "blank": False,
#         }
#         filename = f"TestRequest_{test_request.request_id}.pdf"

#     html = render_to_string("laboratory/requests/pdf_template.html", context)
#     pdf_file = render_to_pdf(html)

#     response = HttpResponse(pdf_file, content_type="application/pdf")
#     response["Content-Disposition"] = f'attachment; filename="{filename}"'
#     return response

