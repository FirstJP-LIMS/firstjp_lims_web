import logging

# Django Core
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone


from ..models import (
    Sample,
)


# Logger Setup
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


# **************
# Phase 2: Sample Examination                 
# **************
@login_required
def sample_examination_list(request):
    """List all samples awaiting verification or processing."""
    samples = Sample.objects.filter(status__in=['AC', 'RJ', 'AP']).select_related('patient', 'test_request')
    return render(request, 'laboratory/examination/sample_list.html', {'samples': samples})


@login_required
def sample_examination_detail(request, sample_id):
    """
    Detail view for verifying a specific sample.
    
    Features:
    - Payment verification before sample acceptance
    - Technician can verify, accept, or reject samples
    - Audit trail of actions
    """
    sample = get_object_or_404(
        Sample.objects.select_related(
            'test_request',
            'test_request__patient',
            'test_request__billing_info',  # 🆕 Needed for payment check
            'vendor'
        ).prefetch_related('test_request__requested_tests'),
        sample_id=sample_id
    )
    
    test_request = sample.test_request  # Fixed: was Sample.test_request (incorrect)

    # ========================================
    # 🆕 CHECK PAYMENT STATUS BEFORE ANY ACTION
    # ========================================
    # Only enforce payment check for verify/accept actions (not reject)
    action = request.POST.get('action') if request.method == 'POST' else None
    
    if action in ['verify', 'accept']:
        # Check if billing exists
        if not hasattr(test_request, 'billing_info'):
            messages.error(
                request,
                f"❌ No billing information found for {test_request.request_id}. "
                f"Please create billing first."
            )
            return redirect('labs:test_request_detail', pk=test_request.pk)
        
        # Check payment status
        if not test_request.is_paid:
            balance_due = test_request.billing_info.get_balance_due()
            
            messages.error(
                request,
                f"🚫 Cannot verify sample for {test_request.request_id}. "
                f"<strong>Payment is required first.</strong><br>"
                f"Outstanding balance: <strong>₦{balance_due:,.2f}</strong>"
            )
            
            # Redirect to payment page
            return redirect('billing:initiate_payment', pk=test_request.billing_info.pk)

    # ========================================
    # HANDLE POST ACTIONS
    # ========================================
    if request.method == 'POST':
        reason = request.POST.get('reason', '').strip()

        # ===========================
        # ACTION 1: VERIFY SAMPLE
        # ===========================
        if action == 'verify':
            # Payment already checked above
            try:
                sample.verify_sample(request.user)
                
                messages.success(
                    request,
                    f"✅ Sample {sample.sample_id} has been verified successfully. "
                    f"Sample is ready for acceptance."
                )
                
                return redirect(reverse('labs:sample-exam-detail', args=[sample.sample_id]))
            
            except Exception as e:
                messages.error(request, f"❌ Error verifying sample: {str(e)}")

        # ===========================
        # ACTION 2: ACCEPT SAMPLE
        # ===========================
        elif action == 'accept':
            # Payment already checked above
            try:
                sample.accept_sample(request.user)
                
                # Update test request status to "Received"
                if test_request.status in ['P', 'A']:  # Pending or Approved
                    test_request.status = 'R'  # Received
                    test_request.save(update_fields=['status'])
                
                messages.success(
                    request,
                    f"✅ Sample {sample.sample_id} accepted and queued for analysis. "
                    f"Test request {test_request.request_id} is now in progress."
                )
                
                return redirect('labs:sample-exam-list')
            
            except Exception as e:
                messages.error(request, f"❌ Error accepting sample: {str(e)}")

        # ===========================
        # ACTION 3: REJECT SAMPLE
        # ===========================
        elif action == 'reject':
            # Rejection doesn't require payment (might be quality issue)
            if not reason:
                messages.error(
                    request,
                    "❌ Please provide a reason for rejecting the sample."
                )
            else:
                try:
                    sample.reject_sample(request.user, reason)
                    
                    messages.warning(
                        request,
                        f"⚠️ Sample {sample.sample_id} has been rejected. "
                        f"Reason: {reason}"
                    )
                    
                    return redirect('labs:sample-exam-list')
                
                except Exception as e:
                    messages.error(request, f"❌ Error rejecting sample: {str(e)}")

    # ========================================
    # GET REQUEST - DISPLAY SAMPLE DETAILS
    # ========================================
    
    # Check payment status for display (non-blocking)
    payment_status = {
        'is_paid': False,
        'billing_exists': False,
        'balance_due': 0,
        'total_amount': 0,
    }
    
    if hasattr(test_request, 'billing_info'):
        billing = test_request.billing_info
        payment_status = {
            'is_paid': test_request.is_paid,
            'billing_exists': True,
            'balance_due': billing.get_balance_due(),
            'total_amount': billing.total_amount,
            'payment_status': billing.get_payment_status_display(),
        }
    
    context = {
        'sample': sample,
        'test_request': test_request,
        'payment_status': payment_status,  # 🆕 For template display
    }
    
    return render(request, 'laboratory/examination/sample_detail.html', context)


# ========================================
# HELPER: Bulk Sample Verification
# ========================================
@login_required
def sample_bulk_verify(request):
    """
    Bulk verify multiple samples at once.
    Useful for batch processing.
    """
    if request.method == 'POST':
        sample_ids = request.POST.getlist('sample_ids')
        
        if not sample_ids:
            messages.warning(request, "⚠️ No samples selected.")
            return redirect('labs:sample-exam-list')
        
        vendor = getattr(request.user, 'vendor', None)
        samples = Sample.objects.filter(
            sample_id__in=sample_ids,
            vendor=vendor
        ).select_related('test_request', 'test_request__billing_info')
        
        verified_count = 0
        payment_blocked_count = 0
        error_count = 0
        
        for sample in samples:
            # Check payment status
            if not sample.test_request.is_paid:
                payment_blocked_count += 1
                continue
            
            try:
                sample.verify_sample(request.user)
                verified_count += 1
            except Exception as e:
                error_count += 1
        
        # Show results
        if verified_count > 0:
            messages.success(
                request,
                f"✅ {verified_count} sample(s) verified successfully."
            )
        
        if payment_blocked_count > 0:
            messages.warning(
                request,
                f"⚠️ {payment_blocked_count} sample(s) blocked due to unpaid bills."
            )
        
        if error_count > 0:
            messages.error(
                request,
                f"❌ {error_count} sample(s) failed verification."
            )
        
        return redirect('labs:sample-exam-list')
    
    return redirect('labs:sample-exam-list')


# ========================================
# HELPER: Override Payment Check (Admin Only)
# ========================================
@login_required
def sample_verify_override_payment(request, sample_id):
    """
    Allow admin to override payment requirement and verify sample.
    Use case: Emergency, payment arrangement, etc.
    
    Requires: vendor_admin role
    """
    vendor = getattr(request.user, 'vendor', None)
    
    # Check if user has permission
    if request.user.role not in ['vendor_admin', 'lab_supervisor']:
        messages.error(
            request,
            "🚫 You don't have permission to override payment requirements."
        )
        return redirect('labs:sample-exam-list')
    
    sample = get_object_or_404(
        Sample.objects.select_related('test_request'),
        sample_id=sample_id,
        vendor=vendor
    )
    
    if request.method == 'POST':
        reason = request.POST.get('override_reason', '').strip()
        
        if not reason:
            messages.error(
                request,
                "❌ Please provide a reason for overriding payment requirement."
            )
        else:
            try:
                # Verify sample without payment check
                sample.verify_sample(request.user)
                
                # Log the override
                from apps.labs.models import AuditLog
                AuditLog.objects.create(
                    vendor=vendor,
                    user=request.user,
                    action=f"PAYMENT OVERRIDE: Verified sample {sample.sample_id} "
                           f"without payment. Reason: {reason}"
                )
                
                messages.warning(
                    request,
                    f"⚠️ Sample {sample.sample_id} verified with payment override. "
                    f"This action has been logged."
                )
                
                return redirect('labs:sample-exam-detail', sample_id=sample.sample_id)
            
            except Exception as e:
                messages.error(request, f"❌ Error: {str(e)}")
    
    context = {
        'sample': sample,
        'test_request': sample.test_request,
    }
    
    return render(request, 'laboratory/examination/payment_override_confirm.html', context)

