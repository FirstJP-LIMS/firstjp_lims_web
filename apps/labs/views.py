"""
PATIENT  →  SAMPLE(S)  →  TEST REQUEST(S)  →  RESULT(S)
   |             |              |                  |
   |          Sample ID      Test ID           Verified / Released
   |             |              |
Doctor → Clinical Info    Department → Test Type

Cost Type,Initial 3-Month Minimum Estimate
Infrastructure (3 months),"$700 - $1,900"
Deployment/CI/CD Setup,"$1,000 - $2,000"
Security Auditing,"$0 - $5,000 (Depends on scope)"
Legal/Compliance Setup,"$5,000 - $10,000"
TOTAL INITIAL LAUNCH BUDGET,"$6,700 - $18,900+"
"""
# apps/labs/views.py
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
    PatientForm, 
    VendorLabTestForm,
    TestRequestForm,
)
from .models import (
    VendorTest, 
    Patient,
    TestRequest,
    Sample,
    TestAssignment,
    Department,
)
from django.core.paginator import Paginator

from django.urls import reverse
from django.contrib.auth.decorators import login_required
from apps.tenants.models import Vendor


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
# dashboard 
@login_required
@tenant_required
def dashboard(request):
    tenant = request.tenant
    is_platform_admin = request.is_platform_admin
    if is_platform_admin and not tenant:
        return render(request, "labs/tenant_index.html")
    # if is_platform_admin and not tenant:
    #     return render(request, "labs/tenant_index.html")
    lab_name = getattr(tenant, 'business_name', tenant.name)
    context = {
        "vendor": tenant,
        "lab_name": lab_name,
        "vendor_domain": tenant.domains.first().domain_name if tenant.domains.exists() else None,
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

    return render(request, "labs/departments/form.html", {"form": form, "action": "Create"})


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

    return render(request, "labs/departments/form.html", {"form": form, "action": "Update"})


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

    return render(request, "labs/departments/confirm_delete.html", {"object": department})

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

    return render(request, "labs/tests/list.html", {"tests": tests})


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

    return render(request, "labs/tests/form.html", {"form": form, "action": "Create"})


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

    return render(request, "labs/tests/form.html", {"form": form, "action": "Update"})


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

    return render(request, "labs/tests/confirm_delete.html", {"object": test})



# @login_required
# def vendor_test_create(request):
#     vendor = request.user.vendor
#     if request.method == "POST":
#         form = VendorTestForm(request.POST, vendor=vendor)
#         if form.is_valid():
#             vendor_test = form.save(commit=False)
#             vendor_test.vendor = vendor
#             vendor_test.enabled = True
#             vendor_test.save()
#             messages.success(request, "Vendor Test created successfully.")
#             return redirect("vendor_tests_list")
#     else:
#         form = VendorTestForm(vendor=vendor)
#     return render(request, "labs/vendor/test_form.html", {"form": form, "title": "Add Vendor Test"})


# @login_required
# def vendor_tests_list(request):
#     # list all VendorTests for the logged-in vendor
#     vendor = request.user.vendor  # assuming a OneToOne relation between user and vendor
#     tests = VendorTest.objects.filter(vendor=vendor)
#     return render(request, "labs/vendor/list_test.html", {"tests": tests})


# @login_required
# def vendor_test_edit(request, slug):
#     # update an existing VendorTest
#     vendor = request.user.vendor
#     vendor_test = get_object_or_404(VendorTest, slug=slug, vendor=vendor)
#     if request.method == "POST":
#         form = VendorTestForm(request.POST, instance=vendor_test, vendor=vendor)
#         if form.is_valid():
#             form.save()
#             messages.success(request, "Vendor Test updated successfully.")
#             return redirect("vendor_tests_list")
#     else:
#         form = VendorTestForm(instance=vendor_test, vendor=vendor)
#     return render(request, "labs/vendor/test_form.html", {"form": form, "title": "Edit Vendor Test"})


# @login_required
# def vendor_test_delete(request, slug):
#     # delete a VendorTest
#     vendor = request.user.vendor
#     vendor_test = get_object_or_404(VendorTest, slug=slug, vendor=vendor)
#     vendor_test.delete()
#     messages.success(request, "Vendor Test deleted successfully.")
#     return redirect("vendor_tests_list")


# ***********************
# Patients / CRUD Operation
# ***********************
@login_required
def patient_list(request):
    vendor = getattr(request.user, 'vendor', None)
    patients = Patient.objects.filter(vendor=vendor)
    return render(request, "labs/patient/patient_list.html", {"patients": patients})

@login_required
def add_patient(request):
    vendor = getattr(request.user, 'vendor', None)
    # Optional: restrict who can add patients
    if not vendor:
        messages.error(request, "Vendor account not found.")
        return redirect("patient_list")

    if request.method == "POST":
        form = PatientForm(request.POST)
        if form.is_valid():
            patient = form.save(commit=False)
            patient.vendor = vendor
            patient.save()
            messages.success(request, f"Patient {patient.patient_id} registered successfully.")
            return redirect("patient_list")
    else:
        form = PatientForm()

    return render(request, "labs/patient/patient_form.html", {"form": form})


# ***********************
# Test Requests / C Operation
# Models involved are: Sample, TestRequest, TestAssignment
# ***********************

@login_required
def create_test_request(request):
    vendor = getattr(request.user, 'vendor', None) or getattr(request, 'tenant', None)
    if not vendor:
        messages.error(request, "Vendor not found for this user.")
        return redirect('dashboard')

    if request.method == 'POST':
        form = TestRequestForm(request.POST, vendor=vendor)
        if form.is_valid():
            try:
                with transaction.atomic():
                    # Get tests before saving
                    tests_to_order = form.cleaned_data['tests_to_order']
                    
                    # Create the request instance
                    request_instance = form.save(commit=False)
                    request_instance.vendor = vendor
                    request_instance.requested_by = request.user
                    
                    # Generate request ID
                    request_instance.request_id = f"REQ-{vendor.requests.count() + 1:04d}"
                    
                    request_instance.save()

                    # Save requested tests
                    request_instance.requested_tests.set(tests_to_order)

                    # Create a sample for the request
                    Sample.objects.create(
                        vendor=vendor,
                        patient=request_instance.patient,
                        specimen_type="Blood",  # You might want to make this dynamic
                        test_request=request_instance,
                        sample_id=f"SMP-{vendor.samples.count() + 1:06d}"
                    )

                    # Create Test Assignments
                    assignments = []
                    for vendor_test in tests_to_order:
                        assignments.append(TestAssignment(
                            vendor=vendor,
                            request=request_instance,
                            global_test=vendor_test.test,
                            vendor_config=vendor_test,
                            department=vendor_test.assigned_department or vendor_test.test.department
                        ))
                    TestAssignment.objects.bulk_create(assignments)

                    messages.success(request, f"Request {request_instance.request_id} created successfully.")
                    return redirect('test_request_list')  # Make sure this URL name matches

            except Exception as e:
                messages.error(request, f"Error creating request: {e}")
                # Log the actual error for debugging
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Test request creation error: {e}")
    else:
        form = TestRequestForm(vendor=vendor)

    return render(request, 'labs/requests/test_request_form.html', {'form': form})




@login_required
def test_request_list(request):
    """
    Displays a paginated list of all TestRequests for the current vendor (tenant).
    """
    vendor = getattr(request.user, 'vendor', None)

    if not vendor:
        messages.error(request, "User is not associated with a vendor/lab.")
        return redirect(reverse_lazy('login')) 

    # 1. Filter the queryset by the current vendor
    # Ordering by -created_at shows the most recent requests first.
    queryset = TestRequest.objects.filter(vendor=vendor).order_by('-created_at').select_related('patient')

    # 2. Add simple pagination
    paginator = Paginator(queryset, 25) # Show 25 requests per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'title': 'All Test Requests',
    }
    
    return render(request, 'labs/requests/test_request_list.html', context)



# apps/lis/views.py

from django.shortcuts import get_object_or_404, render
from django.contrib.auth.decorators import login_required
from .models import TestRequest
from django.db.models import Prefetch

@login_required
def test_request_detail(request, pk):
    """
    Displays the full details of a specific TestRequest, including all assignments.
    """
    vendor = getattr(request.user, 'vendor', None)
    
    # Use Prefetch to retrieve all related models in minimal queries (optimization)
    request_instance = get_object_or_404(
        TestRequest.objects.select_related(
            'patient', 
            'requested_by'
        ).prefetch_related(
            # Fetch all assignments and their related test/department/result data
            Prefetch(
                'assignments', 
                queryset=TestAssignment.objects.select_related(
                    'global_test__department', 
                    'vendor_config', 
                    'result'
                ).order_by('department__name', 'global_test__name')
            ),
            'samples' # Fetch all samples linked to this request
        ),
        pk=pk, 
        vendor=vendor
    )
    
    # Group assignments by department for structured display in the report template
    assignments_by_department = {}
    for assignment in request_instance.assignments.all():
        dept_name = assignment.department.name
        if dept_name not in assignments_by_department:
            assignments_by_department[dept_name] = []
        assignments_by_department[dept_name].append(assignment)

    context = {
        'request_instance': request_instance,
        'patient': request_instance.patient,
        'samples': request_instance.samples.all(),
        'assignments_by_department': assignments_by_department,
        'title': f"Request Details: {request_instance.request_id}",
    }
    
    return render(request, 'labs/requests/test_request_detail.html', context)






# @login_required
# def create_test_request(request):
#     vendor = getattr(request.user, 'vendor', None) or getattr(request, 'tenant', None)
#     if not vendor:
#         messages.error(request, "Vendor not found for this user.")
#         return redirect('dashboard')

#     if request.method == 'POST':
#         form = TestRequestForm(request.POST, vendor=vendor)
#         if form.is_valid():
#             tests_to_order = form.cleaned_data.pop('tests_to_order')

#             try:
#                 with transaction.atomic():
#                     request_instance = form.save(commit=False)
#                     request_instance.vendor = vendor
#                     request_instance.requested_by = request.user
#                     request_instance.save()

#                     # Save requested tests
#                     request_instance.requested_tests.set(tests_to_order)

#                     # Create a sample for the request
#                     Sample.objects.create(
#                         vendor=vendor,
#                         patient=request_instance.patient,
#                         specimen_type="Blood",
#                         test_request=request_instance
#                     )

#                     # Create Test Assignments
#                     assignments = []
#                     for vendor_test in tests_to_order:
#                         assignments.append(TestAssignment(
#                             vendor=vendor,
#                             request=request_instance,
#                             global_test=vendor_test.test,
#                             vendor_config=vendor_test,
#                             department=vendor_test.assigned_department or vendor_test.test.department
#                         ))
#                     TestAssignment.objects.bulk_create(assignments)

#                     messages.success(request, f"Request {request_instance.request_id} created successfully.")
#                     return redirect('lis:test_request_list')

#             except Exception as e:
#                 messages.error(request, f"Error creating request: {e}")
#     else:
#         form = TestRequestForm(vendor=vendor)

#     return render(request, 'labs/requests/test_request_form.html', {'form': form})
