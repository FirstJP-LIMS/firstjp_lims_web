import logging
from decimal import Decimal, InvalidOperation

# Django Core
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from ..models import (
    AuditLog,
    ResultAmendment,
    TestAssignment,
    TestResult,
    Department,
)

from ..decorators import require_capability

# Logger Setup
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def _handle_manual_result_submission(request, assignment, result):
    raw_value = request.POST.get("result_value", "").strip()
    
    if not raw_value:
        messages.error(request, "Result value is required.")
        return _render_manual_result_form(request, assignment, result)

    try:
        with transaction.atomic():
            if result is None:
                # CREATE logic
                result = TestResult.objects.create(
                    assignment=assignment,
                    result_value=raw_value,
                    units=request.POST.get("unit", "").strip(),
                    remarks=request.POST.get("remarks", "").strip(),
                    interpretation=request.POST.get("interpretation", "").strip(),
                    entered_by=request.user,
                    data_source="manual",
                    status="draft",
                )
            else:
                # UPDATE logic (Sync with your update view)
                if result.result_value != raw_value:
                    result.previous_value = result.result_value
                    result.result_value = raw_value
                    result.version += 1

                result.units = request.POST.get("unit", "").strip()
                result.remarks = request.POST.get("remarks", "").strip()
                result.interpretation = request.POST.get("interpretation", "").strip()

            result.auto_flag_result()

            # result.save()

            # Ensure assignment is updated
            assignment.status = 'entered' # Or assignment.mark_analyzed()
            assignment.save()

            messages.success(request, "Result saved successfully.")
            return redirect("labs:result_detail", result_id=result.id)

    except Exception as e:
        messages.error(request, f"Error saving result: {e}")
        print(f"CRITICAL: Failed to save field values: flag={result.flag}, value={result.result_value}")
        return _render_manual_result_form(request, assignment, result)
    

def _render_manual_result_form(request, assignment, result):
    lab_test = assignment.lab_test

    context = {
        "assignment": assignment,
        "lab_test": lab_test,
        "result": result,
        "is_quantitative": lab_test.result_type == "QNT",
        "is_qualitative": lab_test.result_type == "QLT",
        "qualitative_options": lab_test.qlt_options.all()
            if lab_test.result_type == "QLT" else [],
        "default_unit": lab_test.default_units,
    }

    return render(
        request,
        "laboratory/result/manual_result_form.html",
        context,
    )

# ===== RESULT MANUAL CREATE =====
@login_required
@require_capability("can_enter_results")
@require_http_methods(["GET", "POST"])
def enter_manual_result(request, assignment_id):
    """
    Manually enter test result - handles both QUALITATIVE and QUANTITATIVE tests.
    """
    assignment = get_object_or_404(
        TestAssignment.objects.select_related(
            "lab_test", "vendor", "request__patient", "sample"
        ),
        id=assignment_id,
        vendor=request.user.vendor,
    )

    # ❌ Block if result already exists
    if hasattr(assignment, "result"):
        messages.warning(
            request,
            "Result already exists. Use Update Result instead."
        )
        return redirect(
            "labs:update_manual_test_result",
            result_id=assignment.result.id
        )

    if request.method == "POST":
        return _handle_manual_result_submission(
            request=request,
            assignment=assignment,
            result=None,
        )

    return _render_manual_result_form(
        request=request,
        assignment=assignment,
        result=None,
    )


# @login_required
# @require_capability("can_enter_results")
# def update_manual_result(request, result_id):
#     """
#         To be used for manual and instruments generated results
#     """
#     result = get_object_or_404(
#         TestResult.objects.select_related("assignment__lab_test", "assignment__vendor"),
#         id=result_id,
#         assignment__vendor=request.user.vendor,
#     )

#     # ❌ Logic Guard: Only DRAFT results can be updated here
#     if result.status != "draft":
#         messages.error(request, "This result is already verified/released. Please use the Amendment process.")
#         return redirect('labs:result_detail', result_id=result.id)

#     if request.method == "POST":
#         raw_value = request.POST.get("result_value", "").strip()
        
#         if not raw_value:
#             messages.error(request, "Result value is required.")
#         else:
#             try:
#                 with transaction.atomic():
#                     # Update fields
#                     result.result_value = raw_value
#                     result.units = request.POST.get("unit", "").strip()
#                     result.remarks = request.POST.get("remarks", "").strip()
#                     result.interpretation = request.POST.get("interpretation", "").strip()
                    
#                     # Scientific Logic
#                     result.auto_flag_result()
#                     result.save()
                    
#                     # Update Assignment status if it was just 'pending'
#                     if result.assignment.status == 'pending':
#                         result.assignment.status = 'entered'
#                         result.assignment.save()

#                     messages.success(request, "Result updated successfully.")
#                     return redirect("labs:result_detail", result_id=result.id)
#             except Exception as e:
#                 messages.error(request, f"System Error: {str(e)}")

#     return _render_manual_result_form(request, result.assignment, result)

@login_required
@require_capability("can_enter_results")
def update_manual_result(request, result_id):
    result = get_object_or_404(
        TestResult.objects.select_related("assignment__lab_test", "assignment__vendor"),
        id=result_id,
        assignment__vendor=request.user.vendor,
    )

    if result.status != "draft":
        messages.error(request, "This result is already verified. Use Amendment.")
        return redirect('labs:result_detail', result_id=result.id)

    if request.method == "POST":
        # Call the helper!
        return _handle_manual_result_submission(request, result.assignment, result)

    return _render_manual_result_form(request, result.assignment, result)


# # ===== RESULT VIEW =====
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
    
    # Apply filters - ✅ Fixed to use released_at instead of released
    if status_filter == 'pending':
        results = results.filter(verified_at__isnull=True, released_at__isnull=True)
    elif status_filter == 'verified':
        results = results.filter(verified_at__isnull=False, released_at__isnull=True)
    elif status_filter == 'released':
        results = results.filter(released_at__isnull=False)
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
        # Add one day to include the entire end date
        from datetime import datetime, timedelta
        try:
            end_date = datetime.strptime(date_to, '%Y-%m-%d').date() + timedelta(days=1)
            results = results.filter(entered_at__lt=end_date)
        except ValueError:
            results = results.filter(entered_at__lte=date_to)
    
    # Statistics - ✅ Fixed to use released_at
    stats = {
        'total': results.count(),
        'pending_verification': results.filter(verified_at__isnull=True, released_at__isnull=True).count(),
        'verified': results.filter(verified_at__isnull=False, released_at__isnull=True).count(),
        'released': results.filter(released_at__isnull=False).count(),
        'critical': results.filter(flag='C').count(),
        'manual': results.filter(data_source='manual').count(),
        'instrument': results.filter(data_source='instrument').count(),
    }
    
    # Pagination
    paginator = Paginator(results, 30)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    # Get departments for filter dropdown
    departments = Department.objects.filter(vendor=vendor).order_by('name')
    
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
        'departments': departments,
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

    # result_amendments = ResultAmendment.objects.filter(result=result).order_by('-amended_at')
    # result_amendments = get_object_or_404(ResultAmendment.objects.filter(result=result).order_by('-amended_at'))
    # ✅ FIX: Use filter directly. It returns an empty list [] if no amendments exist.
    result_amendments = ResultAmendment.objects.filter(result=result).order_by('-amended_at')

    # ==============================
    # Previous released results (trend)
    # ==============================
    previous_results = (
        TestResult.objects.filter(
            assignment__request__patient=result.assignment.request.patient,
            assignment__lab_test=result.assignment.lab_test,
            status='released',
        )
        .exclude(id=result.id)
        .order_by('-entered_at')[:5]
    )


    # ==============================
    # ACTION PERMISSIONS (ROLE-BASED)
    # ==============================

    # Can edit: draft only
    can_edit = (
        result.status == 'draft'
        and user.can_enter_results
    )

    # Can verify: supervisor+, QC passed, still draft
    can_verify = (
        user.can_verify_results
        and result.status == 'draft'
        and result.qc_passed
    )

    # Can release: pathologist+, verified but not released
    can_release = (
        user.can_release_results
        and result.status == 'verified'
    )

    # Can amend: admin+, released only
    can_amend = (
        user.can_amend_results
        and result.status in ['released', 'amended']
    )

    amendment_count = result.version - 1 if result.version > 1 else 0

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
        'result_amendments': result_amendments,
        'amendment_count': amendment_count,
        'is_amended': result.is_amended,

        # Status helpers
        'is_critical': result.is_critical,
        'has_delta_check': result.delta_flag,
        'workflow_stage': _get_workflow_stage(result),

        # Display helpers
        'user_role': _get_user_role_display(user),
    }

    return render(request, 'laboratory/result/result_detail.html', context)


# ===== VERIFY RELEASE =====
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
    # if result.entered_by == request.user and not request.user.is_vendor_admin:
    #     messages.error(request, "Clinical Safety Violation: You cannot verify a result you entered yourself.")
    #     return redirect('labs:result_detail', result_id=result.id)
    
    if result.verified_at:
        messages.warning(request, "This result has already been verified.")
        # return redirect('labs:result_detail', result_id=result.id)
        return redirect('labs:result_detail', result_id=result.id)

    try:
        with transaction.atomic():
            result.verify(request.user)
            messages.success(request, "Result verified successfully!")

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
    if result.released_at:
        messages.warning(request, "This result has already been released.")
        return redirect('labs:result_detail', result_id=result.id)
    
    try:
        with transaction.atomic():
            # This calls the model method: result.released = True
            result.release(request.user)
            
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
            messages.success(request, "Result released successfully. Ready for patient access.")
        
    except ValidationError as e:
        # This catches errors like "Result must be verified before release"
        messages.error(request, str(e))
    except Exception as e:
        messages.error(request, f"System Error: {str(e)}")
    
    return redirect('labs:result_detail', result_id=result.id)


@login_required
@require_capability("can_amend_results")
def amend_result(request, result_id):
    # Fetch result with related data for the form display
    result = get_object_or_404(
        TestResult.objects.select_related('assignment__lab_test', 'assignment__vendor'), 
        id=result_id, 
        assignment__vendor=request.user.vendor
    )
    
    # 1. State Check: Amendments are only for Released or already Amended results
    if result.status not in ['released', 'amended']:
        messages.error(request, "This result hasn't been released yet. Use the standard edit flow.")
        return redirect('labs:result_detail', result_id=result.id)

    if request.method == "POST":
        new_value = request.POST.get("result_value", "").strip()
        reason = request.POST.get("reason", "").strip()

        # 2. Validation
        if not new_value or not reason:
            messages.error(request, "Both a new value and a formal reason are required for amendments.")
        elif new_value == result.result_value:
            messages.warning(request, "The new value is identical to the current value. No amendment was made.")
            return redirect('labs:result_detail', result_id=result.id)
        else:
            try:
                with transaction.atomic():
                    # Archive the current state before the model method changes it
                    ResultAmendment.objects.create(
                        result=result,
                        old_value=result.result_value,
                        new_value=new_value,
                        reason=reason,
                        amended_by=request.user
                    )

                    # Update the model (handles versioning and status)
                    result.amend(new_value=new_value, user=request.user, reason=reason)
                    
                    AuditLog.objects.create(
                        vendor=request.user.vendor,
                        user=request.user,
                        action=f"AMENDMENT: Result {result.id} (Test: {result.assignment.lab_test.code}) updated.",
                        ip_address=request.META.get('REMOTE_ADDR')
                    )

                    messages.success(request, "Result successfully amended and Corrected Report issued.")
                    return redirect('labs:result_detail', result_id=result.id)
                    
            except Exception as e:
                messages.error(request, f"Critical Error: {str(e)}")

    # GET Request: Show the amendment form
    context = {
        'result': result,
        'lab_test': result.assignment.lab_test,
        'is_quantitative': result.assignment.lab_test.result_type == 'QNT',
    }
    return render(request, 'laboratory/result/amend_result_form.html', context)


def _get_workflow_stage(result):
    if result.status == 'released':
        return 'released'
    elif result.status == 'amended':
        return 'amended'
    elif result.status == 'verified':
        return 'verified'
    elif result.status == 'draft':
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



# @login_required
# @require_capability("can_enter_results")
# @require_http_methods(["GET", "POST"])
# def update_manual_result(request, result_id):
#     result = get_object_or_404(
#         TestResult.objects.select_related(
#             "assignment__lab_test",
#             "assignment__vendor",
#             "assignment__sample",
#         ),
#         id=result_id,
#         assignment__vendor=request.user.vendor,
#     )

#     assignment = result.assignment

#     # ❌ Hard stop if not draft
#     if result.status != "draft":
#         messages.error(
#             request,
#             "Only draft results can be updated."
#         )
#         return redirect(
#             "labs:sample-exam-detail",
#             sample_id=assignment.sample.sample_id,
#         )

#     if request.method == "POST":
#         return _handle_manual_result_submission(
#             request=request,
#             assignment=assignment,
#             result=result,
#         )

#     return _render_manual_result_form(
#         request=request,
#         assignment=assignment,
#         result=result,
#     )


