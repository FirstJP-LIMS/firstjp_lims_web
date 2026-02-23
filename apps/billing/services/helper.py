from ..models import InsuranceProvider, Invoice, BillingInformation

from ..forms import InvoiceForm, InvoicePaymentForm
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect

from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count
from django.utils import timezone

from ..models import Invoice, BillingInformation, InvoicePayment

from ..forms import InvoicePaymentForm
from django.utils import timezone
from datetime import date

import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.db import transaction
from django.utils import timezone
from ..models import BillingInformation, Invoice, InsuranceProvider, D
from ..forms import InvoiceGenerationForm # See below

from ..services.invoice_pdf_view import build_invoice_pdf, build_receipt_pdf

from django.http import HttpResponse
from django.shortcuts import get_object_or_404

logger = logging.getLogger(__name__)

"""
billing/views/invoice_views.py

Real-world invoice workflow:

  Step 1 — SELECT  (GET  /invoices/generate/)
    Staff picks a provider + date range. The view returns unbilled records
    so staff can review them before committing.

  Step 2 — GENERATE (POST /invoices/generate/)
    Staff submits the confirmed selection. The view creates the invoice
    atomically with a collision-safe invoice number.

  Step 3 — MANAGE  (invoice_detail, record_payment, send, cancel)

Design decisions vs the original:
  - @transaction.atomic removed from the GET path (read-only, no transaction needed)
  - Invoice number generated with select_for_update() to prevent race conditions
    when two staff members generate simultaneously
  - corporate_client references removed entirely — InsuranceProvider covers all types
  - invoice_detail no longer references corporate_client FK
  - invoice_list no longer selects corporate_client
  - InvoicePayment recording moved to its own dedicated view
  - Overdue status auto-updated on invoice_list load (a common real-world pattern)
"""


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _generate_invoice_number(vendor, provider) -> str:
    """
    Collision-safe invoice number using select_for_update().

    Format: INV-{PROVIDER_CODE}-{YEAR}-{SEQUENCE:04d}
    Example: INV-AVON-2026-0007

    select_for_update() locks the Invoice table rows for this vendor until
    the transaction commits, preventing two simultaneous requests from
    generating the same number.

    Must be called inside a transaction.atomic() block.
    """
    year = timezone.now().year
    last = (
        Invoice.objects
        .select_for_update()
        .filter(vendor=vendor, invoice_number__startswith=f"INV-{provider.code}-{year}-")
        .order_by('-invoice_number')
        .first()
    )
    if last:
        try:
            seq = int(last.invoice_number.rsplit('-', 1)[-1]) + 1
        except (ValueError, IndexError):
            seq = 1
    else:
        seq = 1

    return f"INV-{provider.code}-{year}-{seq:04d}"


def _auto_mark_overdue(vendor) -> int:
    """
    Mark SENT invoices past their due date as OVERDUE.
    Called on list load — a lightweight background-less alternative to Celery
    for small deployments. Returns count of invoices updated.
    """
    updated = Invoice.objects.filter(
        vendor=vendor,
        status='SENT',
        due_date__lt=timezone.now().date(),
    ).update(status='OVERDUE')
    return updated

