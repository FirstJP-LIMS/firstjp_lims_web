"""
PATIENT  →  SAMPLE(S)  →  TEST REQUEST(S)  →  RESULT(S)
   |             |              |                  |
   |          Sample ID      Test ID           Verified / Released
   |             |              |
Doctor → Clinical Info    Department → Test Type


olas@gmail.com
password#12345  
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

@login_required
def vendor_test_create(request):
    # create a new 
    vendor = request.user.vendor
    if request.method == "POST":
        form = VendorTestForm(request.POST, vendor=vendor)
        if form.is_valid():
            vendor_test = form.save(commit=False)
            vendor_test.vendor = vendor
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
# ***********************
def create_test_request(request):
    vendor = getattr(request.user, 'vendor', None)  # Adjust this if vendor is stored differently

    if request.method == 'POST':
        form = TestRequestForm(request.POST, vendor=vendor)
        if form.is_valid():
            tests_to_order = form.cleaned_data.pop('tests_to_order')
            try:
                with transaction.atomic():
                    # 1. Create TestRequest
                    request_instance = form.save(commit=False)
                    request_instance.vendor = vendor
                    request_instance.save()

                    # 2. Create Sample (default one per request)
                    Sample.objects.create(
                        vendor=vendor,
                        patient=request_instance.patient,
                        specimen_type="Blood",  # You can customize this
                        test_request=request_instance
                    )

                    # 3. Create Test Assignments
                    assignments = []
                    for vendor_test in tests_to_order:
                        assignment = TestAssignment(
                            vendor=vendor,
                            request=request_instance,
                            global_test=vendor_test.test,
                            vendor_config=vendor_test,
                            department=vendor_test.assigned_department or vendor_test.test.department
                        )
                        assignments.append(assignment)

                    TestAssignment.objects.bulk_create(assignments)

                    messages.success(request, f"Request {request_instance.request_id} created with {len(assignments)} tests.")
                    return redirect(reverse_lazy('lis:dashboard'))

            except Exception as e:
                messages.error(request, f"Order creation failed: {e}")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = TestRequestForm(vendor=vendor)

    return render(request, 'labs/requests/test_request_form.html', {'form': form})




