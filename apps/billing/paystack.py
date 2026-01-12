"""
Paystack Payment Gateway Integration for Lab Billing System

Features:
- Initialize payment transactions
- Verify payments
- Handle webhooks
- Multi-tenant support (different API keys per vendor)
"""

import requests
import hmac
import hashlib
import logging
from decimal import Decimal
from django.conf import settings
from django.urls import reverse
from django.utils import timezone

logger = logging.getLogger(__name__)


class PaystackAPI:
    """
    Paystack API wrapper for payment processing.
    
    Usage:
        paystack = PaystackAPI(vendor)
        result = paystack.initialize_payment(billing, callback_url)
    """
    
    BASE_URL = "https://api.paystack.co"
    
    def __init__(self, vendor):
        """
        Initialize Paystack API with vendor-specific credentials.
        
        Args:
            vendor: Vendor instance with payment settings
        """
        self.vendor = vendor
        
        # Get vendor-specific API keys (stored in VendorProfile or settings)
        # Option 1: From vendor profile
        self.secret_key = getattr(
            vendor.profile, 
            'paystack_secret_key', 
            settings.PAYSTACK_SECRET_KEY  # Fallback to global key
        )
        self.public_key = getattr(
            vendor.profile, 
            'paystack_public_key', 
            settings.PAYSTACK_PUBLIC_KEY
        )
        
        self.headers = {
            'Authorization': f'Bearer {self.secret_key}',
            'Content-Type': 'application/json',
        }
    
    def initialize_payment(self, billing, callback_url=None):
        """
        Initialize a payment transaction with Paystack.
        
        Args:
            billing: BillingInformation instance
            callback_url: Optional callback URL for redirect after payment
        
        Returns:
            dict: {
                'success': bool,
                'authorization_url': str,  # URL to redirect user to
                'access_code': str,
                'reference': str,
                'error': str (if failed)
            }
        """
        
        # Convert amount to kobo (Paystack uses smallest currency unit)
        amount_kobo = int(billing.patient_portion * 100)
        
        # Generate unique reference
        reference = f"REQ-{billing.request.request_id}-{timezone.now().strftime('%Y%m%d%H%M%S')}"
        
        # Prepare payload
        payload = {
            'email': billing.request.patient.contact_email or f"{billing.request.patient.patient_id}@example.com",
            'amount': amount_kobo,
            'reference': reference,
            'currency': 'NGN',
            'callback_url': callback_url or self._get_default_callback_url(billing),
            'metadata': {
                'billing_id': billing.id,
                'request_id': billing.request.request_id,
                'patient_name': f"{billing.request.patient.first_name} {billing.request.patient.last_name}",
                'vendor_id': self.vendor.id,
                'vendor_name': self.vendor.name,
            }
        }
        
        try:
            response = requests.post(
                f"{self.BASE_URL}/transaction/initialize",
                json=payload,
                headers=self.headers,
                timeout=10
            )
            
            response.raise_for_status()
            data = response.json()
            
            if data.get('status'):
                return {
                    'success': True,
                    'authorization_url': data['data']['authorization_url'],
                    'access_code': data['data']['access_code'],
                    'reference': data['data']['reference'],
                }
            else:
                logger.error(f"Paystack initialization failed: {data.get('message')}")
                return {
                    'success': False,
                    'error': data.get('message', 'Payment initialization failed')
                }
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Paystack API error: {e}", exc_info=True)
            return {
                'success': False,
                'error': f'Connection error: {str(e)}'
            }
    
    def verify_payment(self, reference):
        """
        Verify a payment transaction.
        
        Args:
            reference: Transaction reference from Paystack
        
        Returns:
            dict: {
                'success': bool,
                'amount': Decimal,
                'status': str ('success', 'failed', 'abandoned'),
                'paid_at': datetime,
                'channel': str,
                'metadata': dict,
                'error': str (if failed)
            }
        """
        
        try:
            response = requests.get(
                f"{self.BASE_URL}/transaction/verify/{reference}",
                headers=self.headers,
                timeout=10
            )
            
            response.raise_for_status()
            data = response.json()
            
            if data.get('status'):
                transaction_data = data['data']
                
                return {
                    'success': True,
                    'amount': Decimal(transaction_data['amount']) / 100,  # Convert from kobo
                    'status': transaction_data['status'],
                    'paid_at': transaction_data.get('paid_at'),
                    'channel': transaction_data.get('channel'),
                    'reference': transaction_data['reference'],
                    'metadata': transaction_data.get('metadata', {}),
                    'customer': transaction_data.get('customer', {}),
                }
            else:
                return {
                    'success': False,
                    'error': data.get('message', 'Verification failed')
                }
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Paystack verification error: {e}", exc_info=True)
            return {
                'success': False,
                'error': f'Verification error: {str(e)}'
            }
    
    def verify_webhook_signature(self, payload, signature):
        """
        Verify Paystack webhook signature for security.
        
        Args:
            payload: Raw request body (bytes)
            signature: X-Paystack-Signature header value
        
        Returns:
            bool: True if signature is valid
        """
        
        computed_signature = hmac.new(
            self.secret_key.encode('utf-8'),
            payload,
            hashlib.sha512
        ).hexdigest()
        
        return hmac.compare_digest(computed_signature, signature)
    
    def _get_default_callback_url(self, billing):
        """Generate default callback URL for payment redirect."""
        from django.contrib.sites.models import Site
        
        # Get current site domain
        domain = Site.objects.get_current().domain
        protocol = 'https' if settings.SECURE_SSL_REDIRECT else 'http'
        
        # Build callback URL
        path = reverse('billing:payment_callback', kwargs={'billing_pk': billing.pk})
        return f"{protocol}://{domain}{path}"


def process_paystack_webhook(request):
    """
    Process Paystack webhook notifications.
    
    This should be called from a webhook view that receives POST requests
    from Paystack when payment status changes.
    
    Args:
        request: Django HttpRequest with webhook payload
    
    Returns:
        tuple: (success: bool, message: str)
    """
    
    # Verify signature
    signature = request.headers.get('X-Paystack-Signature', '')
    
    # Note: Signature verification requires vendor context
    # This is a simplified version - you'll need to determine vendor from payload
    
    try:
        import json
        payload = json.loads(request.body)
        
        event = payload.get('event')
        data = payload.get('data', {})
        
        if event == 'charge.success':
            # Payment successful
            reference = data.get('reference')
            metadata = data.get('metadata', {})
            billing_id = metadata.get('billing_id')
            
            if billing_id:
                from apps.billing.models import BillingInformation, Payment
                
                try:
                    billing = BillingInformation.objects.get(id=billing_id)
                    
                    # Create payment record
                    Payment.objects.create(
                        billing=billing,
                        amount=Decimal(data['amount']) / 100,  # Convert from kobo
                        payment_method='TRANSFER',  # Or map from data['channel']
                        transaction_reference=reference,
                        payment_date=timezone.now(),
                        notes=f"Paystack payment - Channel: {data.get('channel')}"
                    )
                    # Payment.save() automatically updates billing.payment_status
                    
                    logger.info(f"Webhook: Payment recorded for billing {billing_id}")
                    return True, 'Payment processed successfully'
                
                except BillingInformation.DoesNotExist:
                    logger.error(f"Webhook: Billing {billing_id} not found")
                    return False, 'Billing record not found'
        
        return True, 'Event processed'
    
    except Exception as e:
        logger.error(f"Webhook processing error: {e}", exc_info=True)
        return False, str(e)


# ========================================
# VENDOR MODEL EXTENSION
# ========================================
"""
Add these fields to your VendorProfile model:

class VendorProfile(models.Model):
    vendor = models.OneToOneField(Vendor, on_delete=models.CASCADE, related_name='profile')
    
    # Existing fields...
    
    # 🆕 Payment Gateway Settings
    paystack_enabled = models.BooleanField(default=False)
    paystack_public_key = models.CharField(max_length=100, blank=True)
    paystack_secret_key = models.CharField(max_length=100, blank=True)
    
    # Alternative: Flutterwave
    flutterwave_enabled = models.BooleanField(default=False)
    flutterwave_public_key = models.CharField(max_length=100, blank=True)
    flutterwave_secret_key = models.CharField(max_length=100, blank=True)
    
    # General payment settings
    require_payment_before_sample_verification = models.BooleanField(default=True)
    allow_partial_payments = models.BooleanField(default=False)
"""


# ========================================
# SETTINGS.PY ADDITIONS
# ========================================
"""
Add to your settings.py:

# Paystack Configuration (Global fallback)
PAYSTACK_PUBLIC_KEY = env('PAYSTACK_PUBLIC_KEY', default='')
PAYSTACK_SECRET_KEY = env('PAYSTACK_SECRET_KEY', default='')

# Flutterwave Configuration (Alternative)
FLUTTERWAVE_PUBLIC_KEY = env('FLUTTERWAVE_PUBLIC_KEY', default='')
FLUTTERWAVE_SECRET_KEY = env('FLUTTERWAVE_SECRET_KEY', default='')
"""