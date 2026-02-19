import logging

# Django Core
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction
from django.db.models import Sum

from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse

from apps.labs.forms import TestRequestForm, SampleForm
from apps.billing.models import BillingInformation, PriceList

from ..forms import (
    SampleForm,
    TestRequestForm,
)
from ..models import (
    Sample,
    TestRequest,
)
from apps.billing.models import PriceList, BillingInformation

from ..decorators import require_capability


# Logger Setup
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


" LABORATORY_TEST_OPERATION"
# # ***********************
# Phase 1: Test Requests: Test are collected with sample..
# Models involved are: Sample, TestRequest, TestAssignment
# CRUD 
# ***********************

# def is_lab_staff_or_admin(user):
#     return user.role in ["vendor_admin", "lab_supervisor", "lab_technician"]


def ensure_lab_pricing_ready(vendor):
    return PriceList.objects.filter(
        vendor=vendor,
        price_type='RETAIL',
        is_active=True
    ).exists()


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


# @login_required
# @require_capability('can_manage_request')
# def test_request_create(request):
#     """
#     Create a new Test Request and its associated Billing record.
#     Sample collection and lab assignment happen ONLY after
#     payment or admin authorization.
#     """

#     vendor = getattr(request.user, 'vendor', None) or getattr(request, 'tenant', None)
#     if not vendor:
#         messages.error(request, "Vendor not found for this user.")
#         return redirect('dashboard')

#     if not ensure_lab_pricing_ready(vendor):
#         messages.warning(request, "Setup Required: Please create a RETAIL price list before accepting requests.")
#             # Pass 'next' so you can come back here after creation
#         return redirect(f"{reverse('billing:pricelist_create')}?next={request.path}")

#     if request.method == 'POST':
#         request_form = TestRequestForm(
#             request.POST,
#             vendor=vendor,
#             user=request.user
#         )

#         if request_form.is_valid():
#             try:
#                 with transaction.atomic():

#                     # =========================
#                     # STEP 1: Get or Create Patient
#                     # =========================
#                     patient = request_form.get_or_create_patient()

#                     # =========================
#                     # STEP 2: Create Test Request
#                     # =========================
#                     test_request = request_form.save(commit=False)
#                     test_request.vendor = vendor
#                     test_request.patient = patient
#                     test_request.requested_by = request.user

#                     if request.user.role == 'clinician':
#                         test_request.ordering_clinician = request.user

#                     test_request.save()

#                     # Set requested tests (M2M)
#                     tests_to_order = request_form.cleaned_data['tests_to_order']
#                     test_request.requested_tests.set(tests_to_order)

#                     # =========================
#                     # STEP 3: Resolve Pricing Context
#                     # =========================
#                     billing_type = request_form.cleaned_data.get('billing_type', 'CASH')
#                     price_list = None
#                     insurance_provider = None
#                     corporate_client = None

#                     insurance_providers = ['HMO', 'NHIS']
#                     if billing_type in insurance_providers:
#                         insurance_provider = request_form.cleaned_data.get('insurance_provider')
#                         price_list = getattr(insurance_provider, 'price_list', None)

#                     elif billing_type == 'CORPORATE':
#                         corporate_client = request_form.cleaned_data.get('corporate_client')
#                         price_list = getattr(corporate_client, 'price_list', None)

#                     # =========================
#                     # STEP 4: Create Billing Record
#                     # =========================
#                     billing = BillingInformation.objects.create(
#                         vendor=vendor,
#                         request=test_request,
#                         billing_type=billing_type,
#                         price_list=price_list,
#                         insurance_provider=insurance_provider,
#                         corporate_client=corporate_client,
#                         payment_status='UNPAID'
#                     )

#                     # =========================
#                     # SUCCESS → Billing Page
#                     # =========================
#                     messages.success(
#                         request,
#                         (
#                             f"✅ Test request {test_request.request_id} created for "
#                             f"{patient.first_name} {patient.last_name}. "
#                             f"Total: ₦{billing.total_amount:,.2f}. "
#                             "Proceed to billing."
#                         )
#                     )

#                     return redirect(
#                         'billing:billing_detail',
#                         pk=billing.pk
#                     )

#             except Exception as e:
#                 logger = logging.getLogger(__name__)
#                 logger.exception("Error creating test request")

#                 messages.error(
#                     request,
#                     "❌ An unexpected error occurred while creating the test request."
#                 )

#         else:
#             messages.error(request, "❌ Please correct the errors below.")

#     else:
#         request_form = TestRequestForm(
#             vendor=vendor,
#             user=request.user
#         )

#     context = {
#         'form': request_form,
#     }

#     return render(
#         request,
#         'laboratory/requests/request_form.html',
#         context
#     )


# import logging

# from django.contrib import messages
# from django.contrib.auth.decorators import login_required
# from django.db import transaction
# from django.shortcuts import redirect, render
# from django.urls import reverse

# from billing.models import BillingInformation
# from labs.forms import TestRequestForm           # adjust import path as needed
# from labs.utils import ensure_lab_pricing_ready  # adjust import path as needed
# from tenants.decorators import require_capability

# logger = logging.getLogger(__name__)

# Insurance billing types that require an InsuranceProvider FK.
# Kept in one place so the view and form always agree.
INSURANCE_BILLING_TYPES = ['HMO', 'NHIS']


@login_required
@require_capability('can_manage_request')
def test_request_create(request):
    """
    Create a new TestRequest and its associated BillingInformation record.

    Workflow
    ────────
    1.  Resolve vendor from the authenticated user.
    2.  Gate: ensure at least one RETAIL price list exists (billing engine requirement).
    3.  POST → validate form → atomic block:
          a. Get or create Patient
          b. Save TestRequest (vendor / patient / requested_by assigned here)
          c. Set requested_tests M2M
          d. Resolve pricing context (price list, insurance provider, corporate client)
          e. Create BillingInformation — the model's save() triggers _calculate_totals_internal()
    4.  Redirect to the billing detail page so staff can confirm / collect payment.

    Design notes
    ────────────
    - Sample collection and lab assignment happen ONLY after payment or admin authorisation.
    - requested_by is set explicitly in the view (not the form) because the form should not
      have access to request.user directly — it receives it via the `user` kwarg.
    - M2M is set here (not in form.save) because it must happen after test_request.save()
      and after the vendor / patient are already attached.
    """

    # ── Vendor resolution ────────────────────────────────────────────────────
    vendor = getattr(request.user, 'vendor', None) or getattr(request, 'tenant', None)
    if not vendor:
        messages.error(request, "Your account is not associated with a vendor.")
        return redirect('dashboard')

    # ── Pricing gate ─────────────────────────────────────────────────────────
    if not ensure_lab_pricing_ready(vendor):
        messages.warning(
            request,
            "Setup required: please create a RETAIL price list before accepting requests."
        )
        return redirect(
            f"{reverse('billing:pricelist_create')}?next={request.path}"
        )

    # ── Build the form ───────────────────────────────────────────────────────
    form_kwargs = dict(vendor=vendor, user=request.user)

    if request.method == 'POST':
        request_form = TestRequestForm(request.POST, **form_kwargs)

        if request_form.is_valid():
            try:
                with transaction.atomic():

                    # ── STEP 1: Patient ──────────────────────────────────────
                    patient = request_form.get_or_create_patient()

                    # ── STEP 2: TestRequest ──────────────────────────────────
                    test_request = request_form.save(commit=False)
                    test_request.vendor = vendor
                    test_request.patient = patient
                    # requested_by is always the logged-in user; the form sets
                    # ordering_clinician when the user is a clinician.
                    test_request.requested_by = request.user
                    test_request.save()

                    # ── STEP 3: M2M tests ────────────────────────────────────
                    test_request.requested_tests.set(
                        request_form.cleaned_data['tests_to_order']
                    )

                    # ── STEP 4: Resolve billing context ──────────────────────
                    billing_type = request_form.cleaned_data['billing_type']  # always present after is_valid()
                    price_list = None
                    insurance_provider = None
                    corporate_client = None

                    if billing_type in INSURANCE_BILLING_TYPES:
                        insurance_provider = request_form.cleaned_data.get('insurance_provider')
                        # Insurance provider's price list takes precedence
                        price_list = getattr(insurance_provider, 'price_list', None)

                    elif billing_type == 'CORPORATE':
                        corporate_client = request_form.cleaned_data.get('corporate_client')
                        price_list = getattr(corporate_client, 'price_list', None)

                    # CASH / STAFF / NHIS (no provider) → price_list stays None,
                    # which makes BillingInformation use each test's retail price.

                    # ── STEP 5: BillingInformation ───────────────────────────
                    # The model's save() calls _calculate_totals_internal(), which:
                    #   • Sums test prices from the correct price list
                    #   • Applies discounts (price list, corporate, manual)
                    #   • Splits total into patient_portion / insurance_portion
                    billing = BillingInformation.objects.create(
                        vendor=vendor,
                        request=test_request,
                        billing_type=billing_type,
                        price_list=price_list,
                        insurance_provider=insurance_provider,
                        corporate_client=corporate_client,
                        payment_status='UNPAID',
                    )

                    # ── Success ──────────────────────────────────────────────
                    messages.success(
                        request,
                        (
                            f"✅ Test request {test_request.request_id} created for "
                            f"{patient.first_name} {patient.last_name}. "
                            f"Total: ₦{billing.total_amount:,.2f}. "
                            "Proceed to billing."
                        )
                    )
                    return redirect('billing:billing_detail', pk=billing.pk)

            except Exception:
                # Log the full traceback; show a safe message to the user.
                logger.exception(
                    "Unhandled error in test_request_create for vendor=%s user=%s",
                    vendor.pk,
                    request.user.pk,
                )
                messages.error(
                    request,
                    "❌ An unexpected error occurred while creating the test request. "
                    "Our team has been notified."
                )

        else:
            # Form errors are rendered by the template; add a banner for visibility.
            messages.error(request, "❌ Please correct the errors highlighted below.")

    else:
        request_form = TestRequestForm(**form_kwargs)

    return render(
        request,
        'laboratory/requests/request_form.html',
        {'form': request_form},
    )


@login_required
@require_capability("can_manage_request")
def test_request_update(request, pk):
    vendor = getattr(request.user, "vendor", None)
    request_instance = get_object_or_404(TestRequest, pk=pk, vendor=vendor)
    
    # Check if a billing record exists to prevent pricing errors during update
    billing_instance = getattr(request_instance, 'billing_info', None)

    if request.method == "POST":
        form = TestRequestForm(request.POST, instance=request_instance, vendor=vendor)
        
        if form.is_valid():
            try:
                with transaction.atomic():
                    updated_request = form.save()
                    # Update M2M
                    updated_request.requested_tests.set(form.cleaned_data["tests_to_order"])
                    
                    # Update Billing if it exists (Recalculate prices if tests changed)
                    if billing_instance:
                        billing_instance.recalculate_total() # You'll need this method in Billing model
                    
                    messages.success(request, f"Request {updated_request.request_id} updated.")
                    return redirect("labs:test_request_list")
            except Exception as e:
                messages.error(request, f"Update failed: {str(e)}")
    else:
        form = TestRequestForm(instance=request_instance, vendor=vendor)

    return render(request, 'laboratory/requests/request_form.html', {
        "form": form,
        "update_mode": True,
        "instance": request_instance
    })


@login_required
@require_capability("can_manage_request")
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








# @login_required
# @require_capability('can_manage_request')
# def test_request_create(request):
#     """
#     Handles creation of a new Test Request along with linked Sample(s),
#     Patient record, TestAssignments, and Billing Information.
#     """
#     vendor = getattr(request.user, 'vendor', None) or getattr(request, 'tenant', None)
#     if not vendor:
#         messages.error(request, "Vendor not found for this user.")
#         return redirect('dashboard')

#     if request.method == 'POST':
#         # Pass vendor AND user to form
#         request_form = TestRequestForm(request.POST, vendor=vendor, user=request.user)
#         sample_form = SampleForm(request.POST)

#         if request_form.is_valid() and sample_form.is_valid():
#             try:
#                 with transaction.atomic():
#                     # =========================
#                     # STEP 1: Get or Create Patient
#                     # =========================
#                     patient = request_form.get_or_create_patient()

#                     # ==========================
#                     # STEP 2: Create Test Request
#                     # =============================
#                     # Form already handles patient assignment, vendor, user attribution
#                     request_instance = request_form.save(commit=False)
#                     request_instance.vendor = vendor
#                     request_instance.patient = patient
#                     request_instance.requested_by = request.user
                    
#                     # Set ordering_clinician if user is clinician
#                     if request.user.role == 'clinician':
#                         request_instance.ordering_clinician = request.user
                    
#                     request_instance.save()
                    
#                     # Set M2M relationships
#                     tests_to_order = request_form.cleaned_data['tests_to_order']
#                     request_instance.requested_tests.set(tests_to_order)

#                     # ===================
#                     # STEP 3: Create Sample
#                     # ====================
#                     sample = sample_form.save(commit=False)
#                     sample.vendor = vendor
#                     sample.patient = patient
#                     sample.test_request = request_instance
#                     # Auto-generate sample_id if not set
#                     if not sample.sample_id:
#                         sample.sample_id = f"SMP-{vendor.samples.count() + 1:06d}"
#                     sample.save()

#                     # ===============================
#                     # STEP 4: Create Test Assignments
#                     # ================================
#                     assignments = [
#                         TestAssignment(
#                             vendor=vendor,
#                             request=request_instance,
#                             lab_test=vendor_test,
#                             sample=sample,
#                             department=vendor_test.assigned_department,
#                         )
#                         for vendor_test in tests_to_order
#                     ]
#                     TestAssignment.objects.bulk_create(assignments)

#                     # =============================
#                     # STEP 5: AUTO-CREATE BILLING INFORMATION
#                     # =============================
#                     billing_type = request_form.cleaned_data.get('billing_type', 'CASH')
#                     price_list = None
#                     insurance_provider = None
#                     corporate_client = None
                    
#                     # Determine price list and provider based on billing type
#                     if billing_type == 'HMO':
#                         insurance_provider = request_form.cleaned_data.get('insurance_provider')
#                         if insurance_provider and insurance_provider.price_list:
#                             price_list = insurance_provider.price_list
#                     elif billing_type == 'CORPORATE':
#                         corporate_client = request_form.cleaned_data.get('corporate_client')
#                         if corporate_client and corporate_client.price_list:
#                             price_list = corporate_client.price_list
                    
#                     # If no price list set yet, get default RETAIL price list
#                     if not price_list:
#                         price_list = PriceList.objects.filter(
#                             vendor=vendor,
#                             price_type='RETAIL',
#                             is_active=True
#                         ).first()
                    
#                     # Create billing record (totals auto-calculate on save)
#                     billing = BillingInformation.objects.create(
#                         vendor=vendor,
#                         request=request_instance,
#                         billing_type=billing_type,
#                         price_list=price_list,
#                         insurance_provider=insurance_provider,
#                         corporate_client=corporate_client,
#                         payment_status='UNPAID'
#                     )
                    
#                     # ====================
#                     # SUCCESS: Redirect to Payment
#                     # ======================
#                     messages.success(
#                         request,
#                         f"✅ Request {request_instance.request_id} created successfully for "
#                         f"{patient.first_name} {patient.last_name}. "
#                         f"Total Amount: ₦{billing.total_amount:,.2f}. "
#                         f"Please proceed to payment."
#                     )
                    
#                     # Redirect to billing detail page (which has payment button)
#                     return redirect('billing:billing_detail', pk=billing.pk)

#             except Exception as e:
#                 import logging
#                 logger = logging.getLogger(__name__)
#                 logger.error(f"Error creating test request: {e}", exc_info=True)
#                 messages.error(
#                     request, 
#                     f"❌ An error occurred while creating the test request: {str(e)}"
#                 )
                
#         else:
#             # Form validation errors
#             messages.error(request, "❌ Please correct the errors in the forms below.")
            
#             # Debug: Show specific errors
#             if not request_form.is_valid():
#                 for field, errors in request_form.errors.items():
#                     for error in errors:
#                         messages.error(request, f"{field}: {error}")
            
#             if not sample_form.is_valid():
#                 for field, errors in sample_form.errors.items():
#                     for error in errors:
#                         messages.error(request, f"Sample {field}: {error}")
    
#     else:
#         # GET request - show empty forms
#         request_form = TestRequestForm(vendor=vendor, user=request.user)
#         sample_form = SampleForm()

#     context = {
#         'form': request_form,
#         'sample_form': sample_form,
#     }
    
#     return render(request, 'laboratory/requests/request_form.html', context)



# @login_required
# def test_request_create(request):
#     """
#     Handles creation of a new Test Request along with linked Sample(s),
#     Patient record, and TestAssignments.
#     """
#     vendor = getattr(request.user, 'vendor', None) or getattr(request, 'tenant', None)
#     if not vendor:
#         messages.error(request, "Vendor not found for this user.")
#         return redirect('dashboard')

#     if request.method == 'POST':
#         request_form = TestRequestForm(request.POST, vendor=vendor)
#         sample_form = SampleForm(request.POST)

#         if request_form.is_valid() and sample_form.is_valid():
#             try:
#                 with transaction.atomic():
#                     # --- Handle patient (existing or new) ---
#                     patient_data = request_form.cleaned_data.get('patient')
#                     patient = None

#                     if isinstance(patient_data, Patient):
#                         patient = patient_data
#                     elif patient_data is None:
#                         first_name = request_form.cleaned_data.get('first_name')
#                         last_name = request_form.cleaned_data.get('last_name')
#                         if not first_name or not last_name:
#                             raise ValueError("Missing patient information: first name and last name are required.")

#                         patient = Patient.objects.create(
#                             vendor=vendor,
#                             first_name=first_name,
#                             last_name=last_name,
#                             date_of_birth=request_form.cleaned_data.get('date_of_birth'),
#                             gender=request_form.cleaned_data.get('gender'),
#                             contact_email=request_form.cleaned_data.get('contact_email'),
#                             contact_phone=request_form.cleaned_data.get('contact_phone'),
#                         )
#                     else:
#                         raise ValueError("Invalid patient data provided.")

#                     # --- Create Test Request ---
#                     tests_to_order = request_form.cleaned_data['tests_to_order']
#                     request_instance = request_form.save(commit=False)
#                     request_instance.vendor = vendor
#                     request_instance.requested_by = request.user
#                     request_instance.patient = patient
#                     request_instance.request_id = f"REQ-{vendor.requests.count() + 1:04d}"
#                     request_instance.save()
#                     request_instance.requested_tests.set(tests_to_order)

#                     # --- Create Sample from form ---
#                     sample = sample_form.save(commit=False)
#                     sample.vendor = vendor
#                     sample.patient = patient
#                     sample.test_request = request_instance
#                     sample.sample_id = f"SMP-{vendor.samples.count() + 1:06d}"
#                     sample.save()

#                     # --- Create Test Assignments ---
#                     assignments = [
#                         TestAssignment(
#                             vendor=vendor,
#                             request=request_instance,
#                             lab_test=vendor_test,
#                             sample=sample,
#                             department=vendor_test.assigned_department,
#                         )
#                         for vendor_test in tests_to_order
#                     ]
#                     TestAssignment.objects.bulk_create(assignments)

#                     # ==================================
#                     # 🆕 AUTO-CREATE BILLING INFORMATION
#                     # ==================================
#                     billing_type = request_form.cleaned_data.get('billing_type', 'CASH')
#                     price_list = None
#                     insurance_provider = None
#                     corporate_client = None
                    
#                     # Determine price list based on billing type
#                     if billing_type == 'HMO':
#                         insurance_provider = request_form.cleaned_data.get('insurance_provider')
#                         if insurance_provider and insurance_provider.price_list:
#                             price_list = insurance_provider.price_list
#                     elif billing_type == 'CORPORATE':
#                         corporate_client = request_form.cleaned_data.get('corporate_client')
#                         if corporate_client and corporate_client.price_list:
#                             price_list = corporate_client.price_list
#                     else:
#                         # Get default RETAIL price list
#                         price_list = PriceList.objects.filter(
#                             vendor=vendor,
#                             price_type='RETAIL',
#                             is_active=True
#                         ).first()
                    

#                     # Create billing record
#                     billing = BillingInformation.objects.create(
#                         vendor=vendor,
#                         request=request_instance,
#                         billing_type=billing_type,
#                         price_list=price_list,
#                         insurance_provider=insurance_provider,
#                         corporate_client=corporate_client,
#                         payment_status='UNPAID'
#                     )
#                     # Billing totals auto-calculate on save(
#                         # Get default RETAIL price list
#                     messages.success(
#                         request,
#                         f"Request {request_instance.request_id} created successfully for "
#                         f"{patient.first_name} {patient.last_name}."
#                         f"Total Amount: ₦{billing.total_amount:,.2f}. "
#                         f"Please proceed to payment."
#                     )
#                     return redirect('billing:billing_detail')

#             except Exception as e:
#                 import logging
#                 logger = logging.getLogger(__name__)
#                 logger.error(f"Error creating test request: {e}", exc_info=True)
#                 messages.error(request, f"An unexpected error occurred: {e}")
#         else:
#             messages.error(request, "Please correct the errors in the forms below.")
#     else:
#         request_form = TestRequestForm(vendor=vendor)
#         sample_form = SampleForm()

#     return render(request, 'laboratory/requests/request_form.html', {
#         'form': request_form,
#         'sample_form': sample_form,
#     })

