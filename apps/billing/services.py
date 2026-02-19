from django.utils import timezone
from django.db import transaction
from django.db.models import Q
from datetime import timedelta
from decimal import Decimal

from .models import Invoice, BillingInformation, D
# from billing.models import D

def generate_invoice_number(vendor, prefix="INV"):
    today = timezone.now().strftime("%Y%m%d")
    count = Invoice.objects.filter(vendor=vendor).count() + 1
    return f"{prefix}-{today}-{count:04d}"


def generate_hmo_invoice(vendor, insurance_provider, period_start, period_end, user):
    with transaction.atomic():

        billings = BillingInformation.objects.filter(
            vendor=vendor,
            billing_type='HMO',
            insurance_provider=insurance_provider,
            created_at__date__gte=period_start,
            created_at__date__lte=period_end,
            invoice_status='NOT_INVOICED'
        ).filter(
            Q(payment_status='PARTIAL') |
            Q(payment_status='AUTHORIZED') |
            Q(payment_status='INVOICED')
        )

        if not billings.exists():
            return None, "No billings found for this period."

        invoice_number = generate_invoice_number(vendor, prefix="HMO")

        due_date = timezone.now().date() + timedelta(
            days=insurance_provider.payment_terms_days
        )

        invoice = Invoice.objects.create(
            vendor=vendor,
            invoice_number=invoice_number,
            insurance_provider=insurance_provider,
            period_start=period_start,
            period_end=period_end,
            due_date=due_date,
            created_by=user
        )

        invoice.billing_records.set(billings)
        invoice.calculate_totals()

        # mark billings as invoiced
        billings.update(
            payment_status='INVOICED',
            invoice_status='INVOICED'
        )

        invoice.status = 'SENT'
        invoice.save(update_fields=['status'])

        return invoice, None


def generate_corporate_invoice(vendor, corporate_client, period_start, period_end, user):
    with transaction.atomic():

        billings = BillingInformation.objects.filter(
            vendor=vendor,
            billing_type='CORPORATE',
            corporate_client=corporate_client,
            created_at__date__gte=period_start,
            created_at__date__lte=period_end,
            invoice_status='NOT_INVOICED'
        )

        if not billings.exists():
            return None, "No billings found for this period."

        invoice_number = generate_invoice_number(vendor, prefix="CORP")

        due_date = timezone.now().date() + timedelta(
            days=corporate_client.payment_terms_days
        )

        invoice = Invoice.objects.create(
            vendor=vendor,
            invoice_number=invoice_number,
            corporate_client=corporate_client,
            period_start=period_start,
            period_end=period_end,
            due_date=due_date,
            created_by=user
        )

        invoice.billing_records.set(billings)
        invoice.calculate_totals()

        billings.update(
            payment_status='INVOICED',
            invoice_status='INVOICED'
        )

        invoice.status = 'SENT'
        invoice.save(update_fields=['status'])

        return invoice, None

