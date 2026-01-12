import logging
from decimal import Decimal, InvalidOperation

# Django Core
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import (
    Avg, Count, DurationField, ExpressionWrapper, F, Q, Sum, Prefetch
)
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from ..models import (
    AuditLog,
    QualitativeOption,
    TestAssignment,
    TestResult,
)

from ..decorators import require_capability

# Logger Setup
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


# ===== RESULT MANUAL CREATE =====

@login_required
@require_capability("can_enter_results")
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
        return redirect("labs:test_assignment_detail", assignment_id=assignment.id)

    if hasattr(assignment, "result") and assignment.result.verified_at:
        messages.error(
            request,
            "Cannot modify verified result. Contact supervisor for amendments.",
        )
        return redirect("labs:test_assignment_detail", assignment_id=assignment.id)

    lab_test = assignment.lab_test
    is_quantitative = lab_test.result_type == "QNT"
    is_qualitative = lab_test.result_type == "QLT"

    # POST: process submission
    if request.method == "POST":
        # Flag to track if we should proceed with save
        has_validation_errors = False
        
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
                    has_validation_errors = True

        # Required value check
        if not raw_value:
            messages.error(request, "Result value is required.")
            has_validation_errors = True
        
        # Validate quantitative numeric input
        if not has_validation_errors and is_quantitative:
            try:
                numeric_value = Decimal(str(raw_value).strip())
                
                # Optional heuristic warnings (don't block save, just warn)
                if lab_test.min_reference_value:
                    try:
                        if numeric_value < (lab_test.min_reference_value * Decimal("0.1")):
                            messages.warning(request, "Value unusually low — double-check entry.")
                    except Exception:
                        pass
                        
                if lab_test.max_reference_value:
                    try:
                        if numeric_value > (lab_test.max_reference_value * Decimal("10")):
                            messages.warning(request, "Value unusually high — double-check entry.")
                    except Exception:
                        pass
                        
            except (InvalidOperation, ValueError):
                messages.error(request, f"Invalid numeric value: '{raw_value}'.")
                has_validation_errors = True

        # Only proceed if no validation errors
        if not has_validation_errors:
            try:
                with transaction.atomic():
                    # Get or create TestResult
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
                        result.update_result(
                            new_value=raw_value, 
                            user=request.user, 
                            reason="Manual correction"
                        )
                    else:
                        result.result_value = raw_value

                    # Units
                    if is_quantitative:
                        result.units = unit or (lab_test.default_units or "")
                    else:
                        result.units = ""

                    # Qualitative option linking (if field exists on model)
                    if is_qualitative and selected_option:
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
                    
                    # Only set entered_by if this is a new result
                    if created:
                        result.entered_by = request.user

                    result.save()

                    # Apply auto-flagging using your engine (AMR, CRR, panic, ref range, qualitative)
                    result.auto_flag_result()

                    # Mark assignment analyzed (A)
                    assignment.mark_analyzed()

                    # Audit log
                    AuditLog.objects.create(
                        vendor=assignment.vendor,
                        user=request.user,
                        action=(
                            f"Manual result {'entered' if created else 'updated'} for "
                            f"{assignment.request.request_id} - "
                            f"{assignment.lab_test.code}: {result.result_value} "
                            f"{(' ' + result.units) if result.units else ''} "
                            f"[manual]"
                        ),
                        ip_address=request.META.get("REMOTE_ADDR"),
                    )

                    messages.success(
                        request, 
                        f"Result {'saved' if created else 'updated'}. "
                        f"Flag: {result.get_flag_display()}. Awaiting verification."
                    )
                    return redirect("labs:test_assignment_detail", assignment_id=assignment.id)

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


@login_required
@require_capability("can_verify_results")
@require_POST
def verify_result(request, result_id):
    result = get_object_or_404(
        TestResult.objects.select_related('assignment'),
        id=result_id,
        assignment__vendor=request.user.vendor
    )
    
    # SAFETY CHECK: Prevent self-verification
    if result.entered_by == request.user and not request.user.is_vendor_admin:
        messages.error(request, "Clinical Safety Violation: You cannot verify a result you entered yourself.")
        return redirect('labs:result_detail', result_id=result.id)
    
    if result.verified_at:
        messages.warning(request, "This result has already been verified.")
        return redirect('labs:result_detail', result_id=result.id)

    try:
        with transaction.atomic():
            # This calls the model method where you commented out the self-verify check
            result.mark_verified(request.user)
            
            # Audit Log logic...
            messages.success(request, "Result verified successfully!")
            
    except Exception as e:
        messages.error(request, f"Error: {str(e)}")
    
    return redirect('labs:result_detail', result_id=result.id)


# ===== RESULT RELEASE =====
@login_required
@require_capability("can_release_results")
@require_POST
def release_result(request, result_id):
    """
    Release verified result to patient/doctor.
    """
    result = get_object_or_404(
        TestResult.objects.select_related('assignment', 'assignment__vendor'),
        id=result_id,
        assignment__vendor=request.user.vendor
    )
    
    assignment = result.assignment
    
    # Check if it's already released to prevent double-processing
    if result.released:
        messages.warning(request, "This result has already been released.")
        return redirect('labs:result_detail', result_id=result.id)
    
    try:
        with transaction.atomic():
            # This calls the model method: result.released = True
            result.release_result(request.user)
            
            # Audit log
            AuditLog.objects.create(
                vendor=assignment.vendor,
                user=request.user,
                action=(
                    f"Result released for {assignment.request.request_id} - "
                    f"{assignment.lab_test.code}"
                ),
                ip_address=request.META.get('REMOTE_ADDR')
            )
        # Trigger email (ideally this would be a Celery task)
        if result.assignment.request.patient.email:
            send_result_email(result)
            messages.success(request, "Result released and emailed to patient.")
        else:
            messages.success(request, "Result released successfully.")
                        
            messages.success(request, "Result released successfully. Ready for patient access.")
        
    except ValidationError as e:
        # This catches errors like "Result must be verified before release"
        messages.error(request, str(e))
    except Exception as e:
        messages.error(request, f"System Error: {str(e)}")
    
    return redirect('labs:result_detail', result_id=result.id)


# ===== RESULT VIEW =====
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


# ===== RESULT DETAIL (All Lab Staff) =====
@login_required
def result_detail(request, result_id):
    """
    Display detailed view of a single test result.
    Accessible by: All laboratory staff.
    """
    user = request.user

    result = get_object_or_404(
        TestResult.objects.select_related(
            'assignment__lab_test',
            'assignment__request__patient',
            'assignment__request__ordering_clinician',
            'assignment__request__requested_by',
            'assignment__instrument',
            'assignment__department',
            'assignment__sample',
            'entered_by',
            'verified_by',
            'released_by',
        ),
        id=result_id,
        assignment__vendor=user.vendor,
    )

    # ==============================
    # Previous released results (trend)
    # ==============================
    previous_results = (
        TestResult.objects.filter(
            assignment__request__patient=result.assignment.request.patient,
            assignment__lab_test=result.assignment.lab_test,
            released=True,
        )
        .exclude(id=result.id)
        .order_by('-entered_at')[:5]
    )

    # ==============================
    # ACTION PERMISSIONS (ROLE-BASED)
    # ==============================

    # Can edit: result not verified or released, technician+
    can_edit = (
        not result.verified_at
        and not result.released
        and user.can_enter_results
    )

    # Can verify: supervisor+, QC passed, not self-entered
    can_verify = (
        user.can_verify_results
        and not result.verified_at
        and not result.released
        and result.qc_passed
        # and result.entered_by != user  # Optional: allow self-verification if policy allows
    )

    # Can release: pathologist+, already verified, not yet released
    can_release = (
        user.can_release_results
        and result.verified_at
        and not result.released
    )

    # Can amend: released results, admin-only
    can_amend = (
        user.can_amend_results
        and result.released
    )

    # ==============================
    # TEMPLATE CONTEXT
    # ==============================
    context = {
        'result': result,
        'previous_results': previous_results,

        # Action flags
        'can_edit': can_edit,
        'can_verify': can_verify,
        'can_release': can_release,
        'can_amend': can_amend,

        # Status helpers
        'is_critical': result.is_critical,
        'has_delta_check': result.delta_flag,
        'workflow_stage': _get_workflow_stage(result),

        # Display helpers
        'user_role': _get_user_role_display(user),
    }

    return render(request, 'laboratory/result/result_detail.html', context)


# ===== RESULT EDIT =====
@login_required
@require_http_methods(["GET", "POST"])
def edit_result(request, result_id):
    """Edit result before verification."""
    result = get_object_or_404(
        TestResult.objects.select_related(
            'assignment__lab_test',
            'assignment__request__patient'
        ),
        id=result_id,
        assignment__vendor=request.user.vendor
    )

    if result.verified_at:
        messages.error(request, "Cannot edit verified result. Contact supervisor for amendment.")
        return redirect('labs:result_detail', result_id=result.id)

    if result.released:
        messages.error(request, "Cannot edit released result. Use the amendment process.")
        return redirect('labs:result_detail', result_id=result.id)

    test_type = result.assignment.lab_test.result_type
    is_quantitative = test_type == 'QNT'

    if request.method == "POST":
        new_value = request.POST.get("result_value", "").strip()
        units = request.POST.get("units", "").strip()
        remarks = request.POST.get("remarks", "").strip()
        interpretation = request.POST.get("interpretation", "").strip()
        reason = request.POST.get("reason", "").strip()

        if not new_value:
            messages.error(request, "Result value is required.")
            return render(request, 'laboratory/result/edit_result.html', {
                'result': result,
                'is_quantitative': is_quantitative
            })

        if is_quantitative:
            try:
                Decimal(new_value)
            except:
                messages.error(request, "Invalid numeric value for quantitative test.")
                return render(request, 'laboratory/result/edit_result.html', {
                    'result': result,
                    'is_quantitative': is_quantitative
                })

        try:
            with transaction.atomic():
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

                result.auto_flag_result()
                result.check_delta()

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
                return redirect('labs:result_detail', result_id=result.id)

        except Exception as e:
            logger.error(f"Error updating result: {e}", exc_info=True)
            messages.error(request, f"Error: {str(e)}")
        
    context = {
                'result': result,
                'is_quantitative': is_quantitative,
                'action': 'Edit'
            }
    
    return render(request, 'laboratory/result/manual_result_form.html', context)


@login_required
@require_capability("can_amend_results")
@require_POST
def amend_result(request, result_id):
    result = get_object_or_404(TestResult, id=result_id, assignment__vendor=request.user.vendor)
    
    if not result.released:
        messages.error(request, "Use 'Edit' for results that haven't been released yet.")
        return redirect('labs:result_detail', result_id=result.id)

    new_value = request.POST.get("result_value")
    amendment_reason = request.POST.get("reason") # Mandatory for amendments

    if not amendment_reason:
        messages.error(request, "A reason for amendment is legally required.")
        return redirect('labs:result_detail', result_id=result.id)

    try:
        with transaction.atomic():
            # 1. Archive the old data before changing it
            ResultAmendment.objects.create(
                result=result,
                old_value=result.result_value,
                new_value=new_value,
                reason=amendment_reason,
                amended_by=request.user
            )

            # 2. Update the result
            result.result_value = new_value
            result.is_amended = True  # Add this field to your model
            result.save()
            
            messages.success(request, "Result amended. A 'Corrected Report' has been generated.")
            
    except Exception as e:
        messages.error(request, f"Amendment failed: {str(e)}")
    return redirect('labs:result_detail', result_id=result.id)


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


def _get_user_role_display(user):
    """Get friendly display name for user's role"""
    if user.is_vendor_admin:
        return "Laboratory Administrator"
    elif user.is_pathologist:
        return "Pathologist"
    elif user.is_lab_supervisor:
        return "Laboratory Supervisor"
    elif user.is_lab_technician:
        return "Laboratory Technician"
    else:
        return "Laboratory Staff"


# Download Result
from django.conf import settings
from django.template.loader import render_to_string
from django.http import HttpResponse
from weasyprint import HTML
import tempfile

from django.core.mail import EmailMessage


@login_required
def download_result_pdf(request, result_id):
    # Use the same select_related for speed and data access
    result = get_object_or_404(
        TestResult.objects.select_related(
            'assignment__lab_test',
            'assignment__request__patient',
            'assignment__request__ordering_clinician',
            'assignment__sample',
            'verified_by',
        ),
        id=result_id,
        assignment__vendor=request.user.vendor
    )

    # Fetch history just like your detail view does
    previous_results = TestResult.objects.filter(
        assignment__request__patient=result.assignment.request.patient,
        assignment__lab_test=result.assignment.lab_test,
        released=True
    ).exclude(id=result.id).order_by('-entered_at')[:3] # Show last 3 for trend

    context = {
        'result': result,
        'previous_results': previous_results,
        'clinician': result.assignment.request.ordering_clinician,
        # If you have an Amendment model, fetch the latest one
        'amendment': getattr(result, 'amendments', None),
    }

    # Render HTML to string
    html_string = render_to_string('laboratory/result/result_pdf1.html', context)
    html = HTML(string=html_string, base_url=request.build_absolute_uri())
    
    # Generate PDF
    pdf = html.write_pdf()

    response = HttpResponse(pdf, content_type='application/pdf')
    filename = f"Result_{result.assignment.request.request_id}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    return response


def send_result_email(result):
    patient = result.assignment.request.patient
    if not patient.email:
        return False

    subject = f"Laboratory Report - {result.assignment.lab_test.name}"
    body = f"Dear {patient.first_name},\n\nYour test result is ready. Please find the attached report."
    
    # Generate the PDF content
    html_string = render_to_string('laboratory/result/pdf_template.html', {'result': result})
    pdf_content = HTML(string=html_string).write_pdf()

    email = EmailMessage(
        subject,
        body,
        settings.DEFAULT_FROM_EMAIL,
        [patient.email],
    )
    
    # Attach the PDF
    filename = f"Report_{result.assignment.request.request_id}.pdf"
    email.attach(filename, pdf_content, 'application/pdf')
    
    return email.send()


