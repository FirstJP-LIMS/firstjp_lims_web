import logging

# Django Core
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import (
    Avg, Count, DurationField, ExpressionWrapper, F, Q, Sum, Prefetch
)
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

# App-Specific Imports
from apps.accounts.models import VendorProfile
from apps.tenants.models import Vendor

from ..forms import (
    DepartmentForm,
    SampleForm,
    TestRequestForm,
    VendorLabTestForm
)
from ..models import (
    AuditLog,
    Department,
    Equipment,
    Patient,
    QualitativeOption,
    Sample,
    TestAssignment,
    TestRequest,
    TestResult,
    VendorTest
)
from ..services import (
    InstrumentAPIError,
    InstrumentService,
    fetch_assignment_result,
    send_assignment_to_instrument
)
from ..utils import check_tenant_access

from ..decorators import lab_supervisor_required, lab_technician_required


# Logger Setup
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)



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


