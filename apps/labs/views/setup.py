import json
import logging
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from functools import wraps

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
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.db.models import Count, Q

@login_required
@tenant_required
def test_list(request):
    """List lab tests for the current vendor."""
    tenant = getattr(request, "tenant", None)
    is_platform_admin = getattr(request, "is_platform_admin", False)

    if is_platform_admin and not tenant:
        tests = VendorTest.objects.all().select_related("assigned_department", "vendor")
    else:
        tests = VendorTest.objects.filter(vendor=tenant).select_related("assigned_department", "vendor")

    # Calculate statistics
    active_tests_count = tests.filter(enabled=True).count()
    quantitative_count = tests.filter(result_type='QNT').count()
    qualitative_count = tests.filter(result_type='QLT').count()
    
    # Get vendor info
    vendor = tenant if tenant else None

    # DEBUG: Print first test's values
    if tests.exists():
        first_test = tests.first()
        print(f"DEBUG - Code: {first_test.code}")
        print(f"DEBUG - Name: {first_test.name}")
        print(f"DEBUG - result_type: '{first_test.result_type}'")
        print(f"DEBUG - enabled: {first_test.enabled}")
        print(f"DEBUG - Department: {first_test.assigned_department.name}")
        print(f"DEBUG - Price: {first_test.price}")
    
    context = {
        'tests': tests,
        'vendor': vendor,
        'active_tests_count': active_tests_count,
        'quantitative_count': quantitative_count,
        'qualitative_count': qualitative_count,
    }
    
    return render(request, "laboratory/tests/list.html", context)


@login_required
@tenant_required
def test_create(request):
    """Create a vendor-scoped test with proper error handling."""
    tenant = getattr(request, "tenant", None)
    is_platform_admin = getattr(request, "is_platform_admin", False)

    if request.method == "POST":
        form = VendorLabTestForm(request.POST, vendor=tenant)
        
        if form.is_valid():
            test = form.save(commit=False)

            # Determine vendor
            if is_platform_admin and "vendor_id" in request.POST:
                test.vendor = get_object_or_404(Vendor, id=request.POST.get("vendor_id"))
            else:
                test.vendor = tenant

            try:
                # Check if test code already exists for this vendor (before save)
                existing_test = VendorTest.objects.filter(
                    vendor=test.vendor,
                    code=test.code
                ).first()
                
                if existing_test:
                    messages.error(
                        request,
                        f"A test with code '{test.code}' already exists for this vendor. "
                        f"Please use a different code or edit the existing test."
                    )
                    # Add error to form field
                    form.add_error('code', f"Test code '{test.code}' is already in use for this vendor.")
                else:
                    # Safe to save
                    test.save()
                    messages.success(
                        request,
                        f"Test '{test.name}' (Code: {test.code}) added successfully!"
                    )
                    return redirect("labs:test_list")
                    
            except IntegrityError as e:
                # Catch any other integrity errors
                error_message = str(e)
                
                if "UNIQUE constraint failed" in error_message and "code" in error_message:
                    messages.error(
                        request,
                        f"A test with code '{test.code}' already exists. "
                        f"Please use a different code."
                    )
                    form.add_error('code', "This test code is already in use.")
                else:
                    # Generic integrity error
                    messages.error(
                        request,
                        "Unable to create test due to a database constraint. "
                        "Please check all required fields and try again."
                    )
                    
            except Exception as e:
                # Catch any other unexpected errors
                messages.error(
                    request,
                    f"An unexpected error occurred: {str(e)}. Please try again."
                )
    else:
        form = VendorLabTestForm(vendor=tenant)

    # Add vendors for platform admin dropdown
    context = {
        "form": form,
        "action": "Create"
    }
    
    if is_platform_admin and not tenant:
        context["vendors"] = Vendor.objects.all()

    return render(request, "laboratory/tests/form.html", context)


@login_required
@tenant_required
def test_update(request, pk):
    """Update a vendor test with proper error handling."""
    tenant = getattr(request, "tenant", None)
    is_platform_admin = getattr(request, "is_platform_admin", False)

    # Get test and check permissions
    if is_platform_admin and not tenant:
        test = get_object_or_404(VendorTest, pk=pk)
    else:
        test = get_object_or_404(VendorTest, pk=pk, vendor=tenant)

    if request.method == "POST":
        form = VendorLabTestForm(request.POST, instance=test, vendor=test.vendor)
        
        if form.is_valid():
            try:
                updated_test = form.save()
                messages.success(
                    request,
                    f"✓ Test '{updated_test.name}' updated successfully!"
                )
                return redirect("labs:test_list")
                
            except IntegrityError as e:
                error_message = str(e)
                
                if "UNIQUE constraint failed" in error_message and "code" in error_message:
                    messages.error(
                        request,
                        f"⚠ A test with code '{form.cleaned_data.get('code')}' already exists. "
                        f"Please use a different code."
                    )
                    form.add_error('code', "This test code is already in use.")
                else:
                    messages.error(
                        request,
                        "⚠ Unable to update test. Please check all fields and try again."
                    )
                    
            except Exception as e:
                messages.error(
                    request,
                    f"⚠ An unexpected error occurred: {str(e)}"
                )
        else:
            messages.error(
                request,
                "⚠ Please correct the errors below before submitting."
            )
    else:
        form = VendorLabTestForm(instance=test, vendor=test.vendor)

    context = {
        "form": form,
        "test": test,
        "action": "Update",
        "page_title": f"Edit Test: {test.name}"
    }

    return render(request, "laboratory/tests/form.html", context)


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

