
import io
import logging
from email.mime.application import MIMEApplication

from django.core.mail import EmailMultiAlternatives
from django.conf import settings
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.utils import timezone

from ..models import Invoice, InvoicePayment, D
from .invoice_pdf_view import build_invoice_pdf, build_receipt_pdf


"""
billing/services/invoice_email.py

Email service for invoice and receipt delivery.

Architecture:
  - send_invoice_email(invoice)  → attaches invoice PDF, emails provider
  - send_receipt_email(payment)  → attaches receipt PDF, emails provider

Both functions are deliberately separated from views so they can be:
  - Called from Celery tasks later
  - Tested independently
  - Called from management commands for re-sends

"""

logger = logging.getLogger(__name__)



# ── Lazy imports to avoid circular deps ──────────────────────────────────────
def _get_invoice_pdf_builder():
    return build_invoice_pdf


def _get_receipt_pdf_builder():
    return build_receipt_pdf


# ───────────────────────────
# Send Invoice Email
# ─────────────────────────

def send_invoice_email(invoice: Invoice) -> bool:
    """
    Email an invoice PDF to the insurance provider.

    Returns True if the email was sent successfully, False otherwise.
    Never raises — callers should check the return value and show a
    warning if False, but should NOT roll back the status change.
    """
    provider = invoice.insurance_provider
    if not provider or not provider.email:
        logger.warning(
            "Invoice %s: cannot send email — provider has no email address.",
            invoice.invoice_number,
        )
        return False

    try:
        build_pdf = _get_invoice_pdf_builder()
        pdf_bytes = build_pdf(invoice)

        subject = (
            f"Invoice {invoice.invoice_number} — "
            f"₦{invoice.total_amount:,.2f} — "
            f"{invoice.vendor.name}"
        )

        # Plain-text body (fallback for email clients that don't render HTML)
        text_body = render_to_string(
            'billing/invoices/email/invoice_email.txt',
            {
                'invoice':  invoice,
                'provider': provider,
                'vendor':   invoice.vendor,
            }
        )

        # HTML body
        html_body = render_to_string(
            'billing/invoices/email/invoice_email.html',
            {
                'invoice':  invoice,
                'provider': provider,
                'vendor':   invoice.vendor,
            }
        )

        email = EmailMessage(
            subject=subject,
            body=text_body,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'billing@lab.com'),
            to=[provider.email],
            reply_to=[getattr(settings, 'BILLING_REPLY_TO', settings.DEFAULT_FROM_EMAIL)],
        )
        email.content_subtype = 'plain'

        # Attach PDF
        filename = f"Invoice-{invoice.invoice_number}.pdf"
        email.attach(filename, pdf_bytes, 'application/pdf')

        # Attach HTML as alternative
        email.mixed_subtype = 'related'
        from django.core.mail import EmailMultiAlternatives
        email_alt = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=email.from_email,
            to=email.to,
            reply_to=email.reply_to,
        )
        email_alt.attach_alternative(html_body, 'text/html')
        email_alt.attach(filename, pdf_bytes, 'application/pdf')
        email_alt.send(fail_silently=False)

        logger.info(
            "Invoice %s emailed to %s successfully.",
            invoice.invoice_number, provider.email,
        )
        return True

    except Exception:
        logger.exception(
            "Failed to email invoice %s to %s.",
            invoice.invoice_number,
            provider.email if provider else 'unknown',
        )
        return False


# ───────────────────────────────────
# Send Payment Receipt Email
# ────────────────────────────────

def send_receipt_email(payment: InvoicePayment) -> bool:
    """
    Email a payment receipt PDF to the insurance provider.

    Called automatically by record_invoice_payment_view after a successful
    payment is recorded.
    """
    invoice  = payment.invoice
    provider = invoice.insurance_provider

    if not provider or not provider.email:
        logger.warning(
            "Payment %s: cannot send receipt — provider has no email address.",
            payment.pk,
        )
        return False

    try:
        build_pdf = _get_receipt_pdf_builder()
        pdf_bytes = build_pdf(payment)

        subject = (
            f"Payment Receipt — {invoice.invoice_number} — "
            f"₦{payment.amount:,.2f} received — "
            f"{invoice.vendor.name}"
        )

        text_body = render_to_string(
            'billing/invoices/email/receipt_email.txt',
            {
                'payment': payment,
                'invoice': invoice,
                'provider': provider,
                'vendor':   invoice.vendor,
            }
        )

        html_body = render_to_string(
            'billing/invoices/email/receipt_email.html',
            {
                'payment': payment,
                'invoice': invoice,
                'provider': provider,
                'vendor':   invoice.vendor,
            }
        )

        filename = f"Receipt-{invoice.invoice_number}-{payment.payment_date}.pdf"

        email = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'billing@lab.com'),
            to=[provider.email],
        )
        email.attach_alternative(html_body, 'text/html')
        email.attach(filename, pdf_bytes, 'application/pdf')
        email.send(fail_silently=False)

        logger.info(
            "Receipt for payment %s on invoice %s emailed to %s.",
            payment.pk, invoice.invoice_number, provider.email,
        )
        return True

    except Exception:
        logger.exception(
            "Failed to email receipt for payment %s.", payment.pk,
        )
        return False