import logging
from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


# Triggered when a patient Payment is recorded at the front desk
@receiver(post_save, sender='billing.Payment')
def create_rebate_on_patient_payment(sender, instance, created, **kwargs):
    billing = instance.billing
    if billing.referrer_id and billing.is_payment_cleared:
        try:
            record = billing.calculate_and_create_rebate()
            if record:
                logger.info(
                    "Rebate ₦%s created for billing %s → referrer %s",
                    record.rebate_amount, billing.pk, billing.referrer.name,
                )
        except Exception:
            logger.exception(
                "Failed to create rebate record for billing %s", billing.pk
            )


# Triggered when an InvoicePayment propagates back to billing records

@receiver(post_save, sender='billing.InvoicePayment')
def create_rebate_on_insurance_payment(sender, instance, created, **kwargs):
    invoice = instance.invoice
    for billing in invoice.billing_records.filter(referrer__isnull=False):
        if billing.is_payment_cleared:
            try:
                record = billing.calculate_and_create_rebate()
                if record:
                    logger.info(
                        "Rebate ₦%s created for billing %s → referrer %s",
                        record.rebate_amount, billing.pk, billing.referrer.name,
                    )
            except Exception:
                logger.exception(
                    "Failed to create rebate for billing %s on invoice %s",
                    billing.pk, invoice.pk,
                )

