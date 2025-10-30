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
    PatientForm, 
    VendorTestForm, 
    TestRequestForm,
)
from .models import (
    VendorTest, 
    Patient,
    TestRequest,
    Sample,
    TestAssignment,
)
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


# --- CRM Views ---
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
    return render(request, "labs/dashboard.html", context)


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
@login_required
def vendor_tests_list(request):
    # list all VendorTests for the logged-in vendor
    vendor = request.user.vendor  # assuming a OneToOne relation between user and vendor
    tests = VendorTest.objects.filter(vendor=vendor)
    return render(request, "labs/vendor/list_test.html", {"tests": tests})

# @login_required
# def vendor_test_create(request):
#     # create a new 
#     vendor = request.user.vendor
#     if request.method == "POST":
#         form = VendorTestForm(request.POST, vendor=vendor)
#         if form.is_valid():
#             vendor_test = form.save(commit=False)
#             vendor_test.vendor = vendor
#             vendor_test.save()
#             form.is_active = True
#             messages.success(request, "Vendor Test created successfully.")
#             return redirect("vendor_tests_list")
#     else:
#         form = VendorTestForm(vendor=vendor)
#     return render(request, "labs/vendor/test_form.html", {"form": form, "title": "Add Vendor Test"})

@login_required
def vendor_test_create(request):
    vendor = request.user.vendor
    if request.method == "POST":
        form = VendorTestForm(request.POST, vendor=vendor)
        if form.is_valid():
            vendor_test = form.save(commit=False)
            vendor_test.vendor = vendor
            vendor_test.enabled = True
            vendor_test.save()
            messages.success(request, "Vendor Test created successfully.")
            return redirect("vendor_tests_list")
    else:
        form = VendorTestForm(vendor=vendor)
    return render(request, "labs/vendor/test_form.html", {"form": form, "title": "Add Vendor Test"})

@login_required
def vendor_test_edit(request, slug):
    # update an existing VendorTest
    vendor = request.user.vendor
    vendor_test = get_object_or_404(VendorTest, slug=slug, vendor=vendor)
    if request.method == "POST":
        form = VendorTestForm(request.POST, instance=vendor_test, vendor=vendor)
        if form.is_valid():
            form.save()
            messages.success(request, "Vendor Test updated successfully.")
            return redirect("vendor_tests_list")
    else:
        form = VendorTestForm(instance=vendor_test, vendor=vendor)
    return render(request, "labs/vendor/test_form.html", {"form": form, "title": "Edit Vendor Test"})


@login_required
def vendor_test_delete(request, slug):
    # delete a VendorTest
    vendor = request.user.vendor
    vendor_test = get_object_or_404(VendorTest, slug=slug, vendor=vendor)
    vendor_test.delete()
    messages.success(request, "Vendor Test deleted successfully.")
    return redirect("vendor_tests_list")


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