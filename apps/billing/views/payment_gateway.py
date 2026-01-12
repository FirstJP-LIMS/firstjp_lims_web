# apps/billing/views/payment_gateway.py - Add these views
from decimal import Decimal
from datetime import datetime, timedelta, date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import models, transaction
from django.db.models import Q, Sum, Count, Avg, Case, When, DecimalField, F, Value
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy, reverse
from django.utils import timezone

from ..models import (
    PriceList, TestPrice, InsuranceProvider, CorporateClient,
    BillingInformation, Payment, Invoice, InvoicePayment, D
)
from django.views.decorators.csrf import csrf_exempt
from ..forms import (
    PriceListForm, TestPriceForm, InsuranceProviderForm, CorporateClientForm,
    BillingInformationForm, PaymentForm, InvoiceForm, InvoicePaymentForm,
    BillingFilterForm, InvoiceFilterForm
)
# Initialize Paystack payment
from ..paystack import PaystackAPI, process_paystack_webhook

import logging
logger = logging.getLogger(__name__)



@login_required
def initiate_payment_view(request, pk):
    """
    Initiate online payment for a billing record.
    Supports Paystack, Flutterwave, or manual payment.
    """
    vendor = getattr(request.user, "vendor", None)
    if vendor is None:
        raise PermissionDenied("Only vendors can process payments.")
    
    try:
        billing = BillingInformation.objects.select_related(
            'request__patient'
        ).get(pk=pk, vendor=vendor)
    except BillingInformation.DoesNotExist:
        messages.error(request, "Billing record not found.")
        return redirect('billing:billing_list')
    
    # Check if already paid
    if billing.is_fully_paid():
        messages.info(request, "This bill is already fully paid.")
        return redirect('billing:billing_detail', pk=pk)
    
    # Get vendor payment settings
    vendor_profile = getattr(vendor, 'profile', None)
    paystack_enabled = getattr(vendor_profile, 'paystack_enabled', False) if vendor_profile else False
    
    if request.method == 'POST':
        payment_method = request.POST.get('payment_method')
        
        if payment_method == 'online' and paystack_enabled:
            
            paystack = PaystackAPI(vendor)
            result = paystack.initialize_payment(billing)
            
            if result['success']:
                # Store reference for verification
                billing.billing_notes = f"Paystack Ref: {result['reference']}"
                billing.save(update_fields=['billing_notes'])
                
                # Redirect to Paystack payment page
                return redirect(result['authorization_url'])
            else:
                messages.error(request, f"Payment initialization failed: {result['error']}")
        
        elif payment_method == 'manual':
            # Redirect to manual payment form
            return redirect('billing:payment_create', billing_pk=pk)
        
        else:
            messages.error(request, "Invalid payment method selected.")
    
    balance_due = billing.get_balance_due()
    
    context = {
        'billing': billing,
        'balance_due': balance_due,
        'paystack_enabled': paystack_enabled,
    }
    
    return render(request, 'billing/payment/initiate.html', context)


@login_required
def payment_callback_view(request, billing_pk):
    """
    Handle Paystack payment callback after user completes payment.
    """
    vendor = getattr(request.user, "vendor", None)
    
    try:
        billing = BillingInformation.objects.get(pk=billing_pk, vendor=vendor)
    except BillingInformation.DoesNotExist:
        messages.error(request, "Billing record not found.")
        return redirect('billing:billing_list')
    
    # Get reference from query params
    reference = request.GET.get('reference') or request.GET.get('trxref')
    
    if not reference:
        messages.error(request, "No payment reference provided.")
        return redirect('billing:billing_detail', pk=billing_pk)
    
    
    paystack = PaystackAPI(vendor)
    result = paystack.verify_payment(reference)
    
    if result['success'] and result['status'] == 'success':
        # Create payment record
        with transaction.atomic():
            Payment.objects.create(
                billing=billing,
                amount=result['amount'],
                payment_method='TRANSFER',
                transaction_reference=reference,
                payment_date=timezone.now(),
                collected_by=request.user,
                notes=f"Paystack payment - Channel: {result.get('channel', 'online')}"
            )
            # Payment.save() updates billing.payment_status automatically
        
        messages.success(
            request,
            f"Payment of ₦{result['amount']:,.2f} received successfully! "
            f"Sample verification can now proceed."
        )
        return redirect('labs:test_request_detail', pk=billing.request.pk)
    
    elif result['success'] and result['status'] in ['failed', 'abandoned']:
        messages.warning(
            request,
            f"Payment {result['status']}. Please try again or use a different payment method."
        )
    else:
        messages.error(
            request,
            f"Payment verification failed: {result.get('error', 'Unknown error')}"
        )
    
    return redirect('billing:billing_detail', pk=billing_pk)


@csrf_exempt  # Paystack will POST to this
def paystack_webhook_view(request):
    """
    Receive Paystack webhook notifications.
    This handles automatic payment updates.
    """
    if request.method != 'POST':
        return HttpResponse(status=405)
    
    # Process webhook    
    success, message = process_paystack_webhook(request)
    
    if success:
        return HttpResponse(status=200)
    else:
        logger.error(f"Webhook failed: {message}")
        return HttpResponse(status=400)


