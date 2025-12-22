# apps.labs/signals.py
import django.dispatch
from django.dispatch import receiver
from django.db.models.signals import post_save
from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone
from .models import TestRequest, TestResult
from apps.accounts.models import User
import logging

logger = logging.getLogger(__name__)

# Define custom signals
test_request_created = django.dispatch.Signal()
results_verified = django.dispatch.Signal()
results_released_to_patient = django.dispatch.Signal()
critical_result_detected = django.dispatch.Signal()


# ================== AUTO-TRIGGER ON MODEL SAVES ==================

@receiver(post_save, sender=TestRequest)
def test_request_post_save_handler(sender, instance, created, **kwargs):
    """
    Automatically trigger notifications when TestRequest is created/updated.
    """
    if created:
        # New order created - notify lab staff
        try:
            notify_lab_new_order(instance)
        except Exception as e:
            logger.error(f"Failed to send new order notification: {e}")
        
        # If urgent, send urgent notification
        if instance.priority == 'urgent':
            try:
                notify_lab_urgent_order(instance)
            except Exception as e:
                logger.error(f"Failed to send urgent order notification: {e}")
    
    # Check status changes
    elif instance.status == 'V' and instance.verified_at:
        # Results just verified - notify ordering clinician
        if instance.ordering_clinician and not instance.clinician_notified_at:
            try:
                notify_clinician_results_ready(instance)
            except Exception as e:
                logger.error(f"Failed to notify clinician: {e}")


@receiver(post_save, sender=TestResult)
def test_result_post_save_handler(sender, instance, created, **kwargs):
    """
    Check for critical values when results are saved.
    """
    # Only trigger on release and if critical
    if instance.released and instance.flag == 'C':
        test_request = instance.assignment.request
        
        # Check if we haven't already notified for critical results
        if test_request.ordering_clinician and not test_request.clinician_notified_at:
            try:
                notify_critical_result(test_request, instance)
            except Exception as e:
                logger.error(f"Failed to send critical result notification: {e}")


# ================== NOTIFICATION FUNCTIONS ==================

def notify_lab_new_order(test_request):
    """
    Notify lab staff when new order is placed by patient/clinician.
    """
    vendor = test_request.vendor
    
    # Get lab staff emails
    lab_staff = User.objects.filter(
        vendor=vendor,
        role__in=['lab_staff', 'vendor_admin'],
        is_active=True
    )
    
    recipient_emails = [staff.email for staff in lab_staff if staff.email]
    
    if not recipient_emails:
        logger.warning(f"No lab staff emails found for vendor {vendor.name}")
        return
    
    # Determine order source
    if test_request.ordering_clinician:
        source = f"Dr. {test_request.ordering_clinician.get_full_name()}"
        source_type = "Clinician Order"
    elif test_request.is_patient_order:
        source = f"{test_request.patient.first_name} {test_request.patient.last_name}"
        source_type = "Patient Self-Order"
    else:
        source = "Lab Staff"
        source_type = "Walk-in Registration"
    
    # Get test list
    tests_list = test_request.requested_tests.all()[:10]
    tests_text = '\n'.join([f"  • {test.name} ({test.code})" for test in tests_list])
    
    if test_request.requested_tests.count() > 10:
        tests_text += f"\n  ... and {test_request.requested_tests.count() - 10} more"
    
    subject = f"🆕 New Test Order: {test_request.request_id}"
    
    message = f"""New test order received

Order Details:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Order ID: {test_request.request_id}
Patient: {test_request.patient.first_name} {test_request.patient.last_name} ({test_request.patient.patient_id})
Ordered by: {source} ({source_type})
Priority: {test_request.get_priority_display().upper()}
Number of Tests: {test_request.requested_tests.count()}

Tests Ordered:
{tests_text}

{'⚠️ URGENT ORDER - Immediate attention required!' if test_request.priority == 'urgent' else ''}
{'⚠️ REQUIRES APPROVAL - Patient self-order needs physician review' if test_request.requires_approval else ''}

View order: {settings.SITE_URL}/laboratory/requests/{test_request.pk}/

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{vendor.name} Laboratory Information System
"""
    
    try:
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            recipient_emails,
            fail_silently=False,
        )
        logger.info(f"New order notification sent for {test_request.request_id}")
    except Exception as e:
        logger.error(f"Failed to send email for order {test_request.request_id}: {e}")


def notify_lab_urgent_order(test_request):
    """
    Send URGENT notification for STAT orders.
    """
    vendor = test_request.vendor
    
    # Get lab managers/supervisors
    lab_managers = User.objects.filter(
        vendor=vendor,
        role__in=['vendor_admin'],
        is_active=True
    )
    
    for manager in lab_managers:
        # Send SMS if configured and contact available
        if hasattr(manager, 'contact_phone') and manager.contact_phone:
            try:
                send_sms(
                    to=manager.contact_phone,
                    message=f"🚨 URGENT LAB ORDER {test_request.request_id} - Patient: {test_request.patient.patient_id}. Reason: {test_request.urgency_reason[:100]}"
                )
            except Exception as e:
                logger.error(f"Failed to send SMS to {manager.email}: {e}")


def notify_clinician_results_ready(test_request):
    """
    Notify ordering clinician that results are ready.
    """
    clinician = test_request.ordering_clinician
    
    if not clinician or not clinician.email:
        logger.warning(f"No clinician or email for order {test_request.request_id}")
        return
    
    # Check if critical results
    critical_results = TestResult.objects.filter(
        assignment__request=test_request,
        released=True,
        flag='C'
    )
    
    has_critical = critical_results.exists()
    
    if has_critical:
        subject = f"🚨 CRITICAL RESULTS AVAILABLE: {test_request.request_id}"
        priority = "CRITICAL - IMMEDIATE ATTENTION REQUIRED"
    else:
        subject = f"✅ Test Results Ready: {test_request.request_id}"
        priority = "Normal"
    
    # Build critical results text
    critical_text = ""
    if has_critical:
        critical_text = '\n\n⚠️⚠️⚠️ THIS ORDER CONTAINS CRITICAL/PANIC VALUES ⚠️⚠️⚠️\n'
        critical_text += 'Please review IMMEDIATELY and contact the patient.\n\n'
        critical_text += 'Critical Results:\n'
        critical_text += '\n'.join([
            f"  • {r.assignment.lab_test.name}: {r.formatted_result} ({r.get_flag_display()})" 
            for r in critical_results
        ])
    
    message = f"""Dear Dr. {clinician.last_name},

Test results are now available for your patient.

Patient Information:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Name: {test_request.patient.first_name} {test_request.patient.last_name}
Patient ID: {test_request.patient.patient_id}
DOB: {test_request.patient.date_of_birth or 'N/A'}

Order Details:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Order ID: {test_request.request_id}
Order Date: {test_request.created_at.strftime('%B %d, %Y')}
Result Date: {test_request.verified_at.strftime('%B %d, %Y %I:%M %p')}
Status: {priority}

Tests Completed:
{chr(10).join([f"  • {test.name}" for test in test_request.requested_tests.all()])}
{critical_text}

View full results: {settings.SITE_URL}/clinician/results/{test_request.pk}/

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{test_request.vendor.name} Laboratory
"""
    
    try:
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [clinician.email],
            fail_silently=False,
        )
        
        # Mark as notified
        test_request.clinician_notified_at = timezone.now()
        test_request.save(update_fields=['clinician_notified_at'])
        
        logger.info(f"Clinician notified for order {test_request.request_id}")
        
        # If critical, also send SMS
        if has_critical and hasattr(clinician, 'contact_phone') and clinician.contact_phone:
            send_sms(
                to=clinician.contact_phone,
                message=f"🚨 CRITICAL LAB RESULTS for patient {test_request.patient.patient_id}. Order: {test_request.request_id}. Please review immediately."
            )
    except Exception as e:
        logger.error(f"Failed to notify clinician for order {test_request.request_id}: {e}")


def notify_patient_results_ready(test_request):
    """
    Notify patient that results are ready to view online.
    """
    patient = test_request.patient
    
    # Check if patient has user account
    if not hasattr(patient, 'patientuser'):
        logger.info(f"Patient {patient.patient_id} has no user account - skipping notification")
        return
    
    patient_user = patient.patientuser
    user = patient_user.user
    
    if not user.email:
        logger.warning(f"Patient user has no email for patient {patient.patient_id}")
        return
    
    subject = f"✅ Your Lab Results Are Ready - Order {test_request.request_id}"
    
    tests_text = '\n'.join([f"  • {test.name}" for test in test_request.requested_tests.all()])
    
    message = f"""Dear {patient.first_name},

Your lab test results are now available to view online.

Order Information:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Order ID: {test_request.request_id}
Tests Completed: {test_request.requested_tests.count()}
Result Date: {test_request.verified_at.strftime('%B %d, %Y')}

Tests:
{tests_text}

View Your Results: {settings.SITE_URL}/patient/results/{test_request.pk}/

Important Notes:
- Review your results with your healthcare provider
- Do not use these results for self-diagnosis
- Contact us if you have questions: {test_request.vendor.contact_phone or 'N/A'}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{test_request.vendor.name}
"""
    
    try:
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
        )
        
        logger.info(f"Patient notified for order {test_request.request_id}")
        
        # Send SMS if configured
        if hasattr(patient_user, 'preferred_notification'):
            if patient_user.preferred_notification in ['sms', 'both'] and patient.contact_phone:
                send_sms(
                    to=patient.contact_phone,
                    message=f"Your lab results for order {test_request.request_id} are ready. View at: {settings.SITE_URL}/patient/results/{test_request.pk}/"
                )
    except Exception as e:
        logger.error(f"Failed to notify patient for order {test_request.request_id}: {e}")


def notify_critical_result(test_request, test_result):
    """
    Immediate notification for critical/panic values.
    """
    if test_request.ordering_clinician:
        notify_clinician_results_ready(test_request)
    else:
        # No clinician - notify lab staff to contact patient
        logger.warning(f"Critical result for patient order {test_request.request_id} - no clinician assigned")


# ================== SMS HELPER FUNCTION ==================

def send_sms(to, message):
    """
    Send SMS via Twilio (or your preferred SMS provider).
    """
    try:
        # Check if SMS is configured
        if not hasattr(settings, 'TWILIO_ACCOUNT_SID'):
            logger.info("SMS not configured - skipping")
            return None
        
        from twilio.rest import Client
        
        account_sid = settings.TWILIO_ACCOUNT_SID
        auth_token = settings.TWILIO_AUTH_TOKEN
        from_number = settings.TWILIO_PHONE_NUMBER
        
        if not all([account_sid, auth_token, from_number]):
            logger.info("SMS credentials incomplete - skipping")
            return None
        
        client = Client(account_sid, auth_token)
        
        sms = client.messages.create(
            body=message,
            from_=from_number,
            to=to
        )
        
        logger.info(f"SMS sent to {to}: {sms.sid}")
        return sms.sid
        
    except ImportError:
        logger.warning("Twilio library not installed - SMS disabled")
        return None
    except Exception as e:
        logger.error(f"SMS send failed: {str(e)}")
        return None


