import json
import logging
# Django Core
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views.decorators.http import require_http_methods, require_POST

# App-Specific Imports
from ..models import (
    AuditLog,
    Equipment,
    TestAssignment,
)
from ..services.instruments import (
    InstrumentAPIError,
    InstrumentService,
    fetch_assignment_result,
    send_assignment_to_instrument
)


# Logger Setup
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ===== NEW: INSTRUMENT ASSIGNMENT VIEWS =====

@login_required
@require_POST
def assign_instrument(request, assignment_id):
    """
    Assign or reassign instrument to a test assignment (AJAX endpoint)
    """
    try:
        # Parse JSON body
        data = json.loads(request.body)
        instrument_id = data.get('instrument_id')
        
        # Get assignment
        assignment = get_object_or_404(
            TestAssignment,
            id=assignment_id,
            vendor=request.user.vendor
        )
        
        # Validation: Can only assign to pending/in-progress assignments
        if assignment.status not in ['P', 'I']:
            return JsonResponse({
                'success': False,
                'message': f'Cannot assign instrument. Test is in {assignment.get_status_display()} status.'
            }, status=400)
        
        # If already queued to instrument, prevent reassignment
        if assignment.status == 'Q':
            return JsonResponse({
                'success': False,
                'message': 'Cannot reassign. Test already queued to instrument.'
            }, status=400)
        
        with transaction.atomic():
            old_instrument = assignment.instrument
            
            if instrument_id:
                # Assign new instrument
                instrument = get_object_or_404(
                    Equipment,
                    id=instrument_id,
                    vendor=request.user.vendor
                )
                
                # Check instrument status
                if instrument.status != 'active':
                    return JsonResponse({
                        'success': False,
                        'message': f'Instrument {instrument.name} is not active.'
                    }, status=400)
                
                assignment.instrument = instrument
                action_text = f"Assigned to {instrument.name}"
                
            else:
                # Unassign instrument
                assignment.instrument = None
                action_text = "Unassigned instrument"
            
            assignment.save(update_fields=['instrument'])
            
            # Create audit log
            AuditLog.objects.create(
                vendor=request.user.vendor,
                user=request.user,
                action=(
                    f"Instrument assignment: {assignment.request.request_id} - "
                    f"{assignment.lab_test.code} | "
                    f"From: {old_instrument.name if old_instrument else 'None'} → "
                    f"To: {assignment.instrument.name if assignment.instrument else 'None'}"
                ),
                ip_address=request.META.get('REMOTE_ADDR')
            )
        
        return JsonResponse({
            'success': True,
            'message': action_text,
            'instrument_name': assignment.instrument.name if assignment.instrument else None
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'message': 'Invalid JSON data'
        }, status=400)
    
    except Exception as e:
        logger.error(f"Error assigning instrument: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=500)

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
    Bulk assign instrument to multiple assignments
    """
    assignment_ids = request.POST.getlist('assignment_ids[]')
    instrument_id = request.POST.get('instrument_id')
    
    if not assignment_ids:
        messages.error(request, "No assignments selected.")
        return redirect('labs:test_assignment_list')
    
    if not instrument_id:
        messages.error(request, "Please select an instrument.")
        return redirect('labs:test_assignment_list')
    
    try:
        instrument = get_object_or_404(
            Equipment,
            id=instrument_id,
            vendor=request.user.vendor,
            status='active'
        )
        
        with transaction.atomic():
            # Get assignments
            assignments = TestAssignment.objects.filter(
                id__in=assignment_ids,
                vendor=request.user.vendor,
                status__in=['P', 'I']  # Only pending or in-progress
            )
            
            updated_count = 0
            for assignment in assignments:
                assignment.instrument = instrument
                assignment.save(update_fields=['instrument'])
                updated_count += 1
            
            # Create audit log
            AuditLog.objects.create(
                vendor=request.user.vendor,
                user=request.user,
                action=f"Bulk assigned {updated_count} assignments to {instrument.name}",
                ip_address=request.META.get('REMOTE_ADDR')
            )
            
            messages.success(
                request,
                f"Successfully assigned {updated_count} test(s) to {instrument.name}."
            )
            
    except Exception as e:
        logger.error(f"Bulk assignment error: {e}", exc_info=True)
        messages.error(request, f"Error: {str(e)}")
    
    return redirect('labs:test_assignment_list')


@login_required
@require_POST
def auto_assign_instruments(request):
    """
    Automatically assign instruments to pending assignments based on:
    1. Test department
    2. Instrument availability
    3. API configuration (prefer API-enabled)
    """
    vendor = request.user.vendor
    
    # Get all pending assignments without instruments
    pending_assignments = TestAssignment.objects.filter(
        vendor=vendor,
        status='P',
        instrument__isnull=True
    ).select_related('lab_test', 'department')
    
    if not pending_assignments.exists():
        messages.info(request, "No pending assignments need instrument assignment.")
        return redirect('labs:test_assignment_list')
    
    assigned_count = 0
    failed_count = 0
    
    with transaction.atomic():
        for assignment in pending_assignments:
            # Try to find suitable instrument
            # Priority 1: Same department, active, has API endpoint
            suitable_instrument = Equipment.objects.filter(
                vendor=vendor,
                department=assignment.department,
                status='active'
            ).exclude(api_endpoint='').first()
            
            if not suitable_instrument:
                # Priority 2: Same department, active (no API required)
                suitable_instrument = Equipment.objects.filter(
                    vendor=vendor,
                    department=assignment.department,
                    status='active'
                ).first()
            
            if suitable_instrument:
                assignment.instrument = suitable_instrument
                assignment.save(update_fields=['instrument'])
                assigned_count += 1
            else:
                failed_count += 1
        
        # Create audit log
        if assigned_count > 0:
            AuditLog.objects.create(
                vendor=vendor,
                user=request.user,
                action=f"Auto-assigned instruments to {assigned_count} assignments (Smart routing)",
                ip_address=request.META.get('REMOTE_ADDR')
            )
    
    if assigned_count > 0:
        messages.success(
            request,
            f"✅ Successfully auto-assigned {assigned_count} test(s) to instruments."
        )
    
    if failed_count > 0:
        messages.warning(
            request,
            f"⚠️ {failed_count} test(s) could not be assigned. "
            f"No suitable instruments found in their departments."
        )
    
    return redirect('labs:test_assignment_list')

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

# # send_to_instrument - AJAX version 
# @login_required
# @require_POST
# def quick_send_to_instrument(request, assignment_id):
#     """
#     Quick action: Send single assignment to instrument from list view.
#     This is for AJAX calls from the list page.
#     """
#     assignment = get_object_or_404(
#         TestAssignment,
#         id=assignment_id,
#         vendor=request.user.vendor
#     )
    
#     if not assignment.can_send_to_instrument():
#         return JsonResponse({
#             'success': False,
#             'error': 'Cannot send to instrument. Check status and instrument assignment.'
#         }, status=400)
    
#     try:
#         result = send_assignment_to_instrument(assignment_id)
        
#         return JsonResponse({
#             'success': True,
#             'message': f'Sent to {assignment.instrument.name}',
#             'external_id': result.get('id'),
#             'new_status': 'Q',
#             'new_status_display': 'Queued'
#         })
        
#     except InstrumentAPIError as e:
#         return JsonResponse({
#             'success': False,
#             'error': str(e)
#         }, status=500)

