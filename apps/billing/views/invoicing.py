from ..services import generate_hmo_invoice, generate_corporate_invoice
from ..models import InsuranceProvider, CorporateClient, Invoice, BillingInformation

from ..forms import InvoiceForm, InvoicePaymentForm
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect

from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.utils import timezone

from ..models import Invoice, BillingInformation, InvoicePayment

from ..forms import InvoicePaymentForm
from django.utils import timezone
from datetime import date


from django.shortcuts import render, redirect, get_object_or_404
from django.db import transaction
from django.utils import timezone
from ..models import BillingInformation, Invoice, InsuranceProvider
from ..forms import InvoiceGenerationForm # See below


@login_required
@transaction.atomic
def generate_hmo_invoice_final(request):
    # Peer check: Ensure vendor exists to avoid AttributeError
    vendor = getattr(request.user, 'vendor', None)
    if not vendor:
        messages.error(request, "User account is not associated with a vendor.")
        return redirect('dashboard')

    # Initialize form with GET data for filtering or None
    form = InvoiceGenerationForm(request.GET or None, vendor=vendor)
    billable_records = BillingInformation.objects.none()
    
    # 1. HANDLE FILTERING (GET)
    if form.is_valid():
        provider = form.cleaned_data['insurance_provider']
        start_date = form.cleaned_data['start_date']
        end_date = form.cleaned_data['end_date']
        
        billable_records = BillingInformation.objects.filter(
            vendor=vendor,
            insurance_provider=provider,
            created_at__date__range=[start_date, end_date],
            insurance_portion__gt=0,
            payment_status__in=['UNPAID', 'PARTIAL', 'AUTHORIZED']
        ).select_related('request', 'request__patient')

        # --- DEBUG SQL ---
        print(f"Records Found: {billable_records.count()}")
        # Let's see why it's empty if it is
        if not billable_records.exists():
            all_hmo_count = BillingInformation.objects.filter(insurance_provider=provider).count()
            print(f"Total records for this HMO (ignoring dates/status): {all_hmo_count}")
        # --- DEBUG END ---

    # 2. HANDLE CREATION (POST)
    if request.method == 'POST' and 'create_invoice' in request.POST:
        record_ids = request.POST.getlist('record_ids')
        provider_id = request.POST.get('provider_id')
        
        if not record_ids:
            messages.error(request, "No records selected for invoicing.")
        else:
            provider = get_object_or_404(InsuranceProvider, pk=provider_id, vendor=vendor)
            
            # Simple unique number generation
            invoice_count = Invoice.objects.filter(vendor=vendor).count() + 1
            invoice_no = f"INV-{provider.code}-{timezone.now().year}-{invoice_count:04d}"
            
            new_invoice = Invoice.objects.create(
                vendor=vendor,
                invoice_number=invoice_no,
                insurance_provider=provider,
                due_date=timezone.now().date() + timezone.timedelta(days=provider.payment_terms_days),
                period_start=request.POST.get('start_date'),
                period_end=request.POST.get('end_date'),
                created_by=request.user,
                status='DRAFT'
            )
            
            new_invoice.add_billing_records(record_ids)
            
            messages.success(request, f"Invoice {invoice_no} generated successfully.")
            return redirect('billing:invoice_detail', pk=new_invoice.id)

    return render(request, 'billing/invoices/generate_invoice.html', {
        'form': form,
        'records': billable_records,
    })


@login_required
def invoice_detail_view(request, pk):
    vendor = getattr(request.user, 'vendor', None)
    # Ensure we only see invoices belonging to this vendor
    invoice = get_object_or_404(Invoice.objects.select_related(
        'insurance_provider', 
        'corporate_client', 
        'created_by'
    ), pk=pk, vendor=vendor)

    # Get the individual line items (BillingInformation records)
    # This is what the HMO uses to verify the bill
    line_items = invoice.billing_records.select_related('request', 'request__patient').all()

    # Financial Summary
    balance_due = invoice.balance_due()
    is_overdue = invoice.is_overdue()
    
    context = {
        'invoice': invoice,
        'line_items': line_items,
        'balance_due': balance_due,
        'is_overdue': is_overdue,
        'client': invoice.insurance_provider or invoice.corporate_client,
    }
    
    return render(request, 'billing/invoices/invoice_detail.html', context)


# @require_capability('can_manage_billing')
@login_required
def invoice_list_view(request):
    vendor = request.user.vendor

    status_filter = request.GET.get("status")
    start_str = request.GET.get("start")
    end_str = request.GET.get("end")

    invoices = Invoice.objects.filter(vendor=vendor)

    # Status filter
    if status_filter:
        invoices = invoices.filter(status=status_filter)

    # Date range filter
    if start_str and end_str:
        start = date.fromisoformat(start_str)
        end = date.fromisoformat(end_str)
        invoices = invoices.filter(invoice_date__range=(start, end))

    invoices = invoices.select_related(
        "insurance_provider",
        "corporate_client"
    ).order_by("-invoice_date")
    
    # Dashboard metrics
    metrics = {
        "draft": invoices.filter(status="DRAFT").count(),
        "sent": invoices.filter(status="SENT").count(),
        "partial": invoices.filter(status="PARTIAL").count(),
        "paid": invoices.filter(status="PAID").count(),
        "overdue": invoices.filter(status="OVERDUE").count(),
    }

    context = {
        "invoices": invoices,
        "metrics": metrics,
        "status_filter": status_filter,
        "start": start_str,
        "end": end_str,
    }

    return render(request, "billing/invoices/invoice_list.html", context)




# @login_required
# # @require_capability('can_generate_invoice')
# def generate_hmo_invoice_view(request, provider_id):
#     vendor = request.user.vendor
#     provider = get_object_or_404(
#         InsuranceProvider,
#         id=provider_id,
#         vendor=vendor
#     )

#     if request.method == "POST":
#         start = request.POST.get("period_start")
#         end = request.POST.get("period_end")

#         invoice, error = generate_hmo_invoice(
#             vendor,
#             provider,
#             start,
#             end,
#             request.user
#         )

#         if error:
#             messages.warning(request, error)
#         else:
#             messages.success(
#                 request,
#                 f"Invoice {invoice.invoice_number} created. "
#                 f"Total: ₦{invoice.total_amount:,.2f}"
#             )
#             return redirect('billing:invoice_detail', pk=invoice.pk)

#     return render(request, "billing/invoices/hmo_generate.html", {
#         "provider": provider
#     })


# @login_required
# # @require_capability('can_generate_invoice')
# def generate_corporate_invoice_view(request, client_id):
#     vendor = request.user.vendor
#     client = get_object_or_404(
#         CorporateClient,
#         id=client_id,
#         vendor=vendor
#     )

#     if request.method == "POST":
#         start = request.POST.get("period_start")
#         end = request.POST.get("period_end")

#         invoice, error = generate_corporate_invoice(
#             vendor,
#             client,
#             start,
#             end,
#             request.user
#         )

#         if error:
#             messages.warning(request, error)
#         else:
#             messages.success(
#                 request,
#                 f"Invoice {invoice.invoice_number} created. "
#                 f"Total: ₦{invoice.total_amount:,.2f}"
#             )
#             return redirect('billing:invoice_detail', pk=invoice.pk)

#     return render(request, "billing/invoices/corporate_generate.html", {
#         "client": client
#     })


# @login_required
# # @require_capability('can_view_invoice')
# def invoice_detail_view(request, invoice_id):
#     """
#     Display details for a single Invoice (HMO/Corporate).
#     Includes linked billing records, payments, totals, and payment form.
#     """
#     invoice = get_object_or_404(
#         Invoice.objects.prefetch_related('billing_records', 'payments'),
#         id=invoice_id,
#         vendor=request.user.vendor
#     )

#     billing_records = invoice.billing_records.select_related(
#         'request__patient', 'insurance_provider', 'corporate_client'
#     ).all()

#     # Compute invoice totals dynamically (just in case)
#     invoice.calculate_totals()

#     # Compute balance due
#     balance_due = invoice.balance_due()

#     # Payment form
#     if request.method == 'POST':
#         payment_form = InvoicePaymentForm(request.POST)
#         if payment_form.is_valid():
#             payment = payment_form.save(commit=False)
#             payment.invoice = invoice
#             payment.recorded_by = request.user
#             payment.save()
#             # Totals & status updated automatically in InvoicePayment.save()
#             return redirect('billing:invoice_detail', invoice_id=invoice.id)
#         else:
#             messages.error(request, "Please correct the payment errors below.")
#     else:
#         payment_form = InvoicePaymentForm()

#     # Aggregate HMO vs Corporate totals
#     hmo_records = billing_records.filter(billing_type='HMO')
#     corp_records = billing_records.filter(billing_type='CORPORATE')

#     hmo_total = hmo_records.aggregate(total=Sum('insurance_portion'))['total'] or 0
#     corp_total = corp_records.aggregate(total=Sum('total_amount'))['total'] or 0

#     context = {
#         'invoice': invoice,
#         'billing_records': billing_records,
#         'payment_form': payment_form,
#         'balance_due': balance_due,
#         'hmo_total': hmo_total,
#         'corporate_total': corp_total,
#         'total_amount': invoice.total_amount,
#         'amount_paid': invoice.amount_paid,
#         'is_overdue': invoice.is_overdue(),
#     }

#     return render(request, 'billing/invoice/detail.html', context)




# @login_required
# def generate_hmo_invoice(request):
#     vendor = request.user.vendor
#     # Initialize form with GET data or None
#     form = InvoiceGenerationForm(request.GET or None, vendor=vendor)
    
#     billable_records = []
    
#     # If the user has filtered (GET)
#     if form.is_valid():
#         provider = form.cleaned_data['insurance_provider']
#         start = form.cleaned_data['start_date']
#         end = form.cleaned_data['end_date']
        
#         billable_records = BillingInformation.objects.filter(
#             vendor=vendor,
#             insurance_provider=provider,
#             created_at__date__range=[start, end],
#             payment_status__in=['UNPAID', 'PARTIAL', 'AUTHORIZED']
#         )

#     # If the user has submitted the records to create the invoice (POST)
#     if request.method == 'POST' and 'create_invoice' in request.POST:
#         # Get data from POST body instead of function arguments
#         provider_id = request.POST.get('provider_id')
#         # ... proceed with Invoice.objects.create ...

#     return render(request, 'billing/generate_invoice.html', {
#         'form': form,
#         'records': billable_records
#     })


# from ..services import generate_hmo_invoice, generate_corporate_invoice
# from ..models import InsuranceProvider, CorporateClient, Invoice, BillingInformation

# from ..forms import InvoiceForm, InvoicePaymentForm
# from django.contrib import messages
# from django.contrib.auth.decorators import login_required
# from django.shortcuts import render, get_object_or_404, redirect

# from django.shortcuts import get_object_or_404, render, redirect
# from django.contrib.auth.decorators import login_required
# from django.db.models import Sum
# from django.utils import timezone

# from ..models import Invoice, BillingInformation, InvoicePayment

# from ..forms import InvoicePaymentForm
# from django.utils import timezone
# from datetime import date

# from core.decorators import require_capability  # Assuming you have similar decorators

