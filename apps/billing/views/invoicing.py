# ----- Standard library -----
from datetime import date
import logging

# ----- Django core -----
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

# ----- Local app -----
from ..forms import InvoiceGenerationForm, InvoicePaymentForm
from ..models import BillingInformation, InsuranceProvider, Invoice, InvoicePayment, D
from ..services.helper import _auto_mark_overdue, _generate_invoice_number
from ..services.invoice_email import send_invoice_email, send_receipt_email
from ..services.invoice_pdf_view import build_invoice_pdf, build_receipt_pdf

logger = logging.getLogger(__name__)

"""

Invoice workflow:

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


# ────────────────────────────────────
# STEP 1 + 2 — Generate Invoice
# ───────────────────────────────────

"""
billing/views/invoice_views.py — generate_invoice_view

Bug fixed:
  count=Sum('id'.replace('id','1'))  →  this evaluates to Sum('1') at runtime,
  Django cannot resolve '1' as a field name → FieldError.
  Fixed to Count('id') which is the correct ORM expression for COUNT(*).
"""

@login_required
def generate_invoice_view(request):
    """
    Two-phase invoice generation:

    GET  → show provider/date filter form + preview of billable records
    POST → atomically create invoice from confirmed record selection
    """
    vendor = getattr(request.user, 'vendor', None)
    if not vendor:
        messages.error(request, "Vendor account required.")
        return redirect('dashboard')

    # ── GET: filter and preview ───────────────────────────────────────────
    if request.method == 'GET':
        form = InvoiceGenerationForm(request.GET or None, vendor=vendor)
        billable_records = BillingInformation.objects.none()
        selected_provider = None
        summary = None

        if form.is_valid():
            provider   = form.cleaned_data['insurance_provider']
            start_date = form.cleaned_data['start_date']
            end_date   = form.cleaned_data['end_date']
            selected_provider = provider

            billable_records = (
                BillingInformation.objects
                .filter(
                    vendor=vendor,
                    insurance_provider=provider,
                    created_at__date__range=[start_date, end_date],
                    insurance_portion__gt=0,
                    payment_status__in=['UNPAID', 'PARTIAL', 'AUTHORIZED'],
                )
                .select_related('request', 'request__patient')
                .order_by('created_at')
            )

            # FIX: Sum('id'.replace('id','1')) evaluated to Sum('1') → FieldError.
            # Use Count('id') for row count, Sum() for money fields.
            agg = billable_records.aggregate(
                total_insurance=Sum('insurance_portion'),
                total_patient=Sum('patient_portion'),
                total_contract=Sum('total_amount'),
                record_count=Count('id'),          # ← correct
            )
            summary = {
                'record_count':    agg['record_count']              or 0,
                'total_insurance': D(agg['total_insurance']         or 0),
                'total_patient':   D(agg['total_patient']           or 0),
                'total_contract':  D(agg['total_contract']          or 0),
            }

            if not billable_records.exists():
                messages.info(
                    request,
                    f"No unbilled records found for {provider.name} "
                    f"in the selected date range. Records may already be invoiced "
                    f"or have zero insurance portion."
                )

        return render(request, 'billing/invoices/generate_invoice1.html', {
            'form':              form,
            'records':           billable_records,
            'selected_provider': selected_provider,
            'summary':           summary,
        })

    # ── POST: create invoice ──────────────────────────────────────────────
    if request.method == 'POST':
        record_ids  = request.POST.getlist('record_ids')
        provider_id = request.POST.get('provider_id')
        start_date  = request.POST.get('start_date')
        end_date    = request.POST.get('end_date')

        if not record_ids:
            messages.error(request, "No records were selected. Please select at least one record.")
            return redirect('billing:generate_invoice')

        provider = get_object_or_404(InsuranceProvider, pk=provider_id, vendor=vendor)

        try:
            with transaction.atomic():
                invoice_number = _generate_invoice_number(vendor, provider)

                invoice = Invoice.objects.create(
                    vendor=vendor,
                    invoice_number=invoice_number,
                    insurance_provider=provider,
                    invoice_date=timezone.now().date(),
                    due_date=(
                        timezone.now().date()
                        + timezone.timedelta(days=provider.payment_terms_days)
                    ),
                    period_start=start_date,
                    period_end=end_date,
                    created_by=request.user,
                    status='DRAFT',
                )

                invoice.add_billing_records(record_ids)

                if invoice.total_amount == 0:
                    raise ValueError(
                        "None of the selected records had an eligible insurance portion. "
                        "They may have already been invoiced."
                    )

            messages.success(
                request,
                f"Invoice {invoice_number} created for {provider.name} "
                f"— ₦{invoice.total_amount:,.2f} across "
                f"{invoice.billing_records.count()} records."
            )
            return redirect('billing:invoice_detail', pk=invoice.pk)

        except ValueError as e:
            messages.error(request, str(e))
        except Exception:
            logger.exception(
                "Invoice generation failed — vendor=%s provider=%s",
                vendor.pk, provider_id,
            )
            messages.error(request, "An unexpected error occurred. Please try again.")

        return redirect('billing:generate_invoice')
    
# ───────────────────────────
# Invoice Detail
# ──────────────────────────

@login_required
def invoice_detail_view(request, pk):
    vendor = getattr(request.user, 'vendor', None)
    if not vendor:
        messages.error(request, "Vendor account required.")
        return redirect('dashboard')

    invoice = get_object_or_404(
        Invoice.objects.select_related(
            'insurance_provider',   # single payer FK — no corporate_client
            'created_by',
        ),
        pk=pk,
        vendor=vendor,
    )

    line_items = (
        invoice.billing_records
        .select_related('request', 'request__patient')
        .order_by('created_at')
    )

    payments = invoice.payments.select_related('recorded_by').order_by('-payment_date')

    payment_form = InvoicePaymentForm()

    # Financial summary
    balance_due = invoice.balance_due()
    is_overdue  = invoice.is_overdue()

    # Per-billing-type breakdown for line items
    line_summary = line_items.aggregate(
        total_insurance=Sum('insurance_portion'),
        total_patient=Sum('patient_portion'),
        total_contract=Sum('total_amount'),
    )

    context = {
        'invoice':      invoice,
        'provider':     invoice.insurance_provider,   # clean alias for template
        'line_items':   line_items,
        'payments':     payments,
        'payment_form': payment_form,
        'balance_due':  balance_due,
        'is_overdue':   is_overdue,
        'line_summary': line_summary,
        # Status helpers for template conditional rendering
        'can_send':     invoice.status == 'DRAFT',
        'can_pay':      invoice.status in ('SENT', 'PARTIAL', 'OVERDUE'),
        'can_cancel':   invoice.status in ('DRAFT', 'SENT'),
    }

    return render(request, 'billing/invoices/invoice_detail.html', context)


# ──────────────────────────────────────
# Record Payment against an Invoice
# ──────────────────────────────────────

@login_required
def record_invoice_payment_view(request, pk):
    """
    POST-only view. Validates and records an InvoicePayment.
    InvoicePayment.save() propagates to billing records automatically.
    """
    vendor = getattr(request.user, 'vendor', None)
    if not vendor:
        messages.error(request, "Vendor account required.")
        return redirect('dashboard')

    invoice = get_object_or_404(Invoice, pk=pk, vendor=vendor)

    if invoice.status not in ('SENT', 'PARTIAL', 'OVERDUE'):
        messages.error(
            request,
            f"Payments can only be recorded against SENT, PARTIAL, or OVERDUE invoices. "
            f"This invoice is {invoice.get_status_display()}."
        )
        return redirect('billing:invoice_detail', pk=invoice.pk)

    if request.method != 'POST':
        return redirect('billing:invoice_detail', pk=invoice.pk)

    form = InvoicePaymentForm(request.POST)

    if form.is_valid():
        amount = form.cleaned_data['amount']
        balance = invoice.balance_due()

        if amount > balance:
            messages.error(
                request,
                f"Payment amount ₦{amount:,.2f} exceeds the outstanding balance "
                f"₦{balance:,.2f}. Please enter the correct amount."
            )
            return redirect('billing:invoice_detail', pk=invoice.pk)

        try:
            with transaction.atomic():
                payment = form.save(commit=False)
                payment.invoice     = invoice
                payment.recorded_by = request.user
                payment.save()  # triggers InvoicePayment.save() which propagates to billing records

            messages.success(
                request,
                f"Payment of ₦{amount:,.2f} recorded. "
                f"Outstanding balance: ₦{invoice.balance_due():,.2f}."
            )
        except Exception:
            logger.exception("Invoice payment failed — invoice=%s", pk)
            messages.error(request, "Payment could not be recorded. Please try again.")

    else:
        messages.error(request, f"Invalid payment details: {form.errors.as_text()}")

    return redirect('billing:invoice_detail', pk=invoice.pk)


# ────────────────────────────
# Send Invoice (Email)
# ─────────────────────────────

@login_required
def send_invoice_view(request, pk):
    """
    Mark a DRAFT invoice as SENT and email the PDF to the provider.

    The status transition and the email are intentionally decoupled:
    - Status flip is committed first (inside the atomic block)
    - Email is attempted after commit
    - If email fails: status stays SENT, user sees a warning
    - This prevents a broken SMTP config from blocking the entire workflow
    """
    vendor = getattr(request.user, 'vendor', None)
    if not vendor:
        return redirect('dashboard')

    invoice = get_object_or_404(Invoice, pk=pk, vendor=vendor)

    if request.method != 'POST':
        return redirect('billing:invoice_detail', pk=pk)

    if invoice.status != 'DRAFT':
        messages.error(
            request,
            f"Only DRAFT invoices can be sent. "
            f"Current status: {invoice.get_status_display()}."
        )
        return redirect('billing:invoice_detail', pk=pk)

    if invoice.total_amount <= 0:
        messages.error(request, "Cannot send an invoice with zero total amount.")
        return redirect('billing:invoice_detail', pk=pk)

    # ── Commit the status change ──────────────────────────────────────────
    invoice.status = 'SENT'
    invoice.save(update_fields=['status', 'updated_at'])

    # ── Attempt email (non-blocking) ──────────────────────────────────────
    provider = invoice.insurance_provider
    email_sent = send_invoice_email(invoice)

    if email_sent:
        messages.success(
            request,
            f"Invoice {invoice.invoice_number} marked as SENT and emailed to "
            f"{provider.email}. Due date: {invoice.due_date.strftime('%d %b %Y')}."
        )
    else:
        if provider and provider.email:
            messages.warning(
                request,
                f"Invoice {invoice.invoice_number} marked as SENT, but the email "
                f"to {provider.email} could not be delivered. "
                f"Please send the PDF manually — "
                f"<a href=\"{{% url 'billing:invoice_pdf' pk %}}\" class=\"alert-link\">"
                f"Download PDF</a>."
            )
        else:
            messages.success(
                request,
                f"Invoice {invoice.invoice_number} marked as SENT. "
                f"Note: no email address is set for {provider.name if provider else 'this provider'}."
            )

    return redirect('billing:invoice_detail', pk=pk)


@login_required
def record_invoice_payment_view(request, pk):
    """
    Record an InvoicePayment against an invoice, then:
      1. InvoicePayment.save() updates invoice status + propagates to billing records
      2. send_receipt_email() emails a receipt PDF to the provider
      3. Success message links to receipt PDF download
    """
    vendor = getattr(request.user, 'vendor', None)
    if not vendor:
        messages.error(request, "Vendor account required.")
        return redirect('dashboard')

    invoice = get_object_or_404(Invoice, pk=pk, vendor=vendor)

    if invoice.status not in ('SENT', 'PARTIAL', 'OVERDUE'):
        messages.error(
            request,
            f"Payments can only be recorded against SENT, PARTIAL, or OVERDUE invoices. "
            f"This invoice is {invoice.get_status_display()}."
        )
        return redirect('billing:invoice_detail', pk=invoice.pk)

    if request.method != 'POST':
        return redirect('billing:invoice_detail', pk=invoice.pk)

    form = InvoicePaymentForm(request.POST)

    if form.is_valid():
        amount  = form.cleaned_data['amount']
        balance = invoice.balance_due()

        if amount > balance:
            messages.error(
                request,
                f"Payment amount NGN {amount:,.2f} exceeds the outstanding "
                f"balance NGN {balance:,.2f}."
            )
            return redirect('billing:invoice_detail', pk=invoice.pk)

        try:
            with transaction.atomic():
                payment = form.save(commit=False)
                payment.invoice     = invoice
                payment.recorded_by = request.user
                payment.save()  # triggers propagation to billing records

            # ── Receipt email (non-blocking, outside transaction) ─────────
            receipt_sent = send_receipt_email(payment)

            # Build success message with receipt download link
            receipt_url = f"/billing/invoices/{invoice.pk}/payments/{payment.pk}/receipt/"
            new_balance = invoice.balance_due()

            if new_balance <= 0:
                status_text = "Invoice is now fully paid."
            else:
                status_text = f"Remaining balance: NGN {new_balance:,.2f}."

            email_note = ""
            if receipt_sent:
                provider = invoice.insurance_provider
                email_note = f" Receipt emailed to {provider.email}."

            messages.success(
                request,
                f"Payment of NGN {amount:,.2f} recorded. {status_text}{email_note}."
            )

        except Exception:
            logger.exception(
                "Invoice payment failed — invoice=%s vendor=%s", pk, vendor.pk
            )
            messages.error(request, "Payment could not be recorded. Please try again.")

    else:
        messages.error(request, f"Invalid payment details: {form.errors.as_text()}")

    return redirect('billing:invoice_detail', pk=invoice.pk)

# ────────────────────────────────────────────
# Cancel Invoice (DRAFT or SENT → CANCELLED)
# ─────────────────────────────────────────────

@login_required
def cancel_invoice_view(request, pk):
    """
    Cancel an invoice and release attached billing records back to AUTHORIZED
    so they can be re-invoiced.
    """
    vendor = getattr(request.user, 'vendor', None)
    if not vendor:
        return redirect('dashboard')

    invoice = get_object_or_404(Invoice, pk=pk, vendor=vendor)

    if request.method != 'POST':
        return redirect('billing:invoice_detail', pk=pk)

    if invoice.status not in ('DRAFT', 'SENT'):
        messages.error(
            request,
            f"Only DRAFT or SENT invoices can be cancelled. "
            f"Status: {invoice.get_status_display()}."
        )
        return redirect('billing:invoice_detail', pk=pk)

    try:
        with transaction.atomic():
            # Release billing records so they can be included in a future invoice
            invoice.billing_records.filter(
                payment_status='INVOICED'
            ).update(payment_status='AUTHORIZED')

            invoice.status = 'CANCELLED'
            invoice.save(update_fields=['status', 'updated_at'])

        messages.success(
            request,
            f"Invoice {invoice.invoice_number} cancelled. "
            f"Billing records have been released for re-invoicing."
        )
    except Exception:
        logger.exception("Invoice cancellation failed — invoice=%s", pk)
        messages.error(request, "Cancellation failed. Please try again.")

    return redirect('billing:invoice_detail', pk=pk)


# ────────────────────────
# Invoice List
# ────────────────────

@login_required
def invoice_list_view(request):
    """
    List HMOS, NHIS Orgs 
    """
    vendor = getattr(request.user, 'vendor', None)
    if not vendor:
        messages.error(request, "Vendor account required.")
        return redirect('dashboard')

    # Auto-mark overdue invoices before rendering the list
    overdue_count = _auto_mark_overdue(vendor)
    if overdue_count:
        messages.warning(request, f"{overdue_count} invoice(s) marked overdue.")

    invoices = Invoice.objects.filter(vendor=vendor)

    # ── Filters ──────────────────────────────────────────────────────────────
    status_filter   = request.GET.get('status', '').strip()
    provider_filter = request.GET.get('provider', '').strip()
    start_str       = request.GET.get('start', '').strip()
    end_str         = request.GET.get('end', '').strip()

    if status_filter:
        invoices = invoices.filter(status=status_filter)

    if provider_filter:
        invoices = invoices.filter(insurance_provider_id=provider_filter)

    if start_str:
        try:
            invoices = invoices.filter(invoice_date__gte=date.fromisoformat(start_str))
        except ValueError:
            pass

    if end_str:
        try:
            invoices = invoices.filter(invoice_date__lte=date.fromisoformat(end_str))
        except ValueError:
            pass

    invoices = (
        invoices
        .select_related('insurance_provider')   # no corporate_client
        .order_by('-invoice_date')
    )

    # ── Metrics (run on the unfiltered vendor queryset for dashboard accuracy) ─
    all_invoices = Invoice.objects.filter(vendor=vendor)
    metrics = {
        'draft':    all_invoices.filter(status='DRAFT').count(),
        'sent':     all_invoices.filter(status='SENT').count(),
        'partial':  all_invoices.filter(status='PARTIAL').count(),
        'paid':     all_invoices.filter(status='PAID').count(),
        'overdue':  all_invoices.filter(status='OVERDUE').count(),
        'total_outstanding': D(
            all_invoices.filter(status__in=['SENT', 'PARTIAL', 'OVERDUE'])
            .aggregate(s=Sum('total_amount'))['s'] or 0
        ) - D(
            all_invoices.filter(status__in=['SENT', 'PARTIAL', 'OVERDUE'])
            .aggregate(s=Sum('amount_paid'))['s'] or 0
        ),
    }

    # Provider list for filter dropdown
    providers = InsuranceProvider.objects.filter(
        vendor=vendor, is_active=True
    ).order_by('provider_type', 'name')

    context = {
        'invoices':        invoices,
        'metrics':         metrics,
        'providers':       providers,
        # Active filter values (for repopulating the filter form)
        'status_filter':   status_filter,
        'provider_filter': provider_filter,
        'start':           start_str,
        'end':             end_str,
        # Choices for status dropdown
        'status_choices':  Invoice.INVOICE_STATUS,
    }

    return render(request, 'billing/invoices/invoice_list1.html', context)


# ── View ─────────────────────────────────────

@login_required
def download_invoice_pdf_view(request, pk):
    """
    Stream an Invoice as a PDF download.

    URL: /billing/invoices/<uuid:pk>/pdf/
    Name: billing:invoice_pdf
    """
    vendor = getattr(request.user, 'vendor', None)
    if not vendor:
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied

    invoice = get_object_or_404(
        Invoice.objects.select_related(
            'insurance_provider', 'vendor', 'created_by'
        ).prefetch_related(
            'billing_records',
            'billing_records__request',
            'billing_records__request__patient',
        ),
        pk=pk,
        vendor=vendor,
    )

    pdf_bytes = build_invoice_pdf(invoice)

    filename = f"Invoice-{invoice.invoice_number}.pdf"
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
def download_receipt_pdf_view(request, pk, payment_pk):
    """
    Stream a payment receipt as a PDF download.

    URL: /billing/invoices/<uuid:pk>/payments/<uuid:payment_pk>/receipt/
    Name: billing:invoice_receipt
    """
    vendor = getattr(request.user, 'vendor', None)
    if not vendor:
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied

    invoice = get_object_or_404(Invoice, pk=pk, vendor=vendor)
    payment = get_object_or_404(
        InvoicePayment.objects.select_related(
            'invoice', 'invoice__insurance_provider',
            'invoice__vendor', 'recorded_by',
        ).prefetch_related(
            'invoice__billing_records',
        ),
        pk=payment_pk,
        invoice=invoice,
    )

    pdf_bytes = build_receipt_pdf(payment)
    receipt_no = f"RCP-{str(payment.pk).replace('-','').upper()[:8]}"
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = (
        f'attachment; filename="Receipt-{receipt_no}-{invoice.invoice_number}.pdf"'
    )
    return response





# @login_required
# def send_invoice_view(request, pk):
#     """Mark a DRAFT invoice as SENT. POST only."""
#     vendor = getattr(request.user, 'vendor', None)
#     if not vendor:
#         return redirect('dashboard')

#     invoice = get_object_or_404(Invoice, pk=pk, vendor=vendor)

#     if request.method != 'POST':
#         return redirect('billing:invoice_detail', pk=pk)

#     if invoice.status != 'DRAFT':
#         messages.error(request, f"Only DRAFT invoices can be sent. Status: {invoice.get_status_display()}.")
#         return redirect('billing:invoice_detail', pk=pk)

#     if invoice.total_amount <= 0:
#         messages.error(request, "Cannot send an invoice with zero total amount.")
#         return redirect('billing:invoice_detail', pk=pk)

#     invoice.status = 'SENT'
#     invoice.save(update_fields=['status', 'updated_at'])

#     messages.success(
#         request,
#         f"Invoice {invoice.invoice_number} marked as SENT to {invoice.insurance_provider.name}. "
#         f"Due date: {invoice.due_date}."
#     )
#     return redirect('billing:invoice_detail', pk=pk)

