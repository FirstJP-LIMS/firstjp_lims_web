from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import models, transaction
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy, reverse
from django.utils import timezone
from django.views.generic import View
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.core.mail import EmailMessage
from django.conf import settings
from weasyprint import HTML, CSS
from weasyprint.text.fonts import FontConfiguration
import io

from ..models import Invoice, InvoicePayment

from ..models import (
    BillingInformation, Payment, Invoice, InvoicePayment, D
)

from ..forms import InvoiceForm, InvoicePaymentForm, InvoiceFilterForm


from ..utils import generate_invoice_pdf, generate_receipt_pdf


@login_required
def invoice_list(request):
    """List all invoices with filters"""
    vendor = request.user.vendor
    
    # Base queryset
    queryset = Invoice.objects.filter(
        vendor=vendor
    ).select_related(
        'insurance_provider', 'corporate_client', 'created_by'
    ).order_by('-invoice_date')
    
    # Apply filters
    form = InvoiceFilterForm(request.GET)
    if form.is_valid():
        if form.cleaned_data.get('status'):
            queryset = queryset.filter(status=form.cleaned_data['status'])
        
        client_type = form.cleaned_data.get('client_type')
        if client_type == 'HMO':
            queryset = queryset.filter(insurance_provider__isnull=False)
        elif client_type == 'CORPORATE':
            queryset = queryset.filter(corporate_client__isnull=False)
        
        if form.cleaned_data.get('date_from'):
            queryset = queryset.filter(invoice_date__gte=form.cleaned_data['date_from'])
        
        if form.cleaned_data.get('date_to'):
            queryset = queryset.filter(invoice_date__lte=form.cleaned_data['date_to'])
    
    # Check for overdue invoices
    for invoice in queryset:
        if invoice.is_overdue() and invoice.status not in ['PAID', 'CANCELLED']:
            invoice.status = 'OVERDUE'
            invoice.save(update_fields=['status'])
    
    # Pagination
    paginator = Paginator(queryset, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'invoices': page_obj,
        'page_obj': page_obj,
        'filter_form': form,
    }
    
    return render(request, 'billing/invoice_list.html', context)


@login_required
def invoice_detail(request, pk):
    """View invoice details"""
    invoice = get_object_or_404(
        Invoice.objects.select_related(
            'insurance_provider', 'corporate_client'
        ).prefetch_related('billing_records', 'payments'),
        pk=pk,
        vendor=request.user.vendor
    )
    
    context = {
        'invoice': invoice,
        'balance_due': invoice.balance_due(),
        'payment_form': InvoicePaymentForm(invoice=invoice),
    }
    
    return render(request, 'billing/invoice_detail.html', context)


@login_required
def invoice_create(request):
    """Create new invoice"""
    vendor = request.user.vendor
    
    if request.method == 'POST':
        form = InvoiceForm(request.POST, vendor=vendor)
        
        if form.is_valid():
            with transaction.atomic():
                invoice = form.save(commit=False)
                invoice.vendor = vendor
                invoice.created_by = request.user
                
                # Generate invoice number
                last_invoice = Invoice.objects.filter(
                    vendor=vendor
                ).order_by('-id').first()
                
                if last_invoice and last_invoice.invoice_number:
                    try:
                        last_num = int(last_invoice.invoice_number.split('-')[-1])
                        new_num = last_num + 1
                    except (ValueError, IndexError):
                        new_num = 1
                else:
                    new_num = 1
                
                invoice.invoice_number = f"INV-{timezone.now().year}-{new_num:05d}"
                invoice.save()
                
                # Link billing records
                billing_ids = request.POST.getlist('billing_records')
                if billing_ids:
                    billing_records = BillingInformation.objects.filter(
                        id__in=billing_ids,
                        vendor=vendor
                    )
                    invoice.billing_records.set(billing_records)
                    
                    # Calculate totals
                    invoice.calculate_totals()
                
                messages.success(
                    request,
                    f'Invoice {invoice.invoice_number} created successfully.'
                )
                return redirect('billing:invoice_detail', pk=invoice.pk)
    else:
        form = InvoiceForm(vendor=vendor)
    
    # Get pending billing records for invoice generation
    pending_hmo = BillingInformation.objects.filter(
        vendor=vendor,
        billing_type='HMO',
        payment_status='INVOICED',
        invoices__isnull=True
    ).select_related('insurance_provider')
    
    pending_corporate = BillingInformation.objects.filter(
        vendor=vendor,
        billing_type='CORPORATE',
        payment_status='INVOICED',
        invoices__isnull=True
    ).select_related('corporate_client')
    
    context = {
        'form': form,
        'pending_hmo': pending_hmo,
        'pending_corporate': pending_corporate,
    }
    
    return render(request, 'billing/invoice_form.html', context)


@login_required
def invoice_payment_create(request, invoice_pk):
    """Record invoice payment"""
    invoice = get_object_or_404(
        Invoice,
        pk=invoice_pk,
        vendor=request.user.vendor
    )
    
    if request.method == 'POST':
        form = InvoicePaymentForm(request.POST, invoice=invoice)
        
        if form.is_valid():
            with transaction.atomic():
                payment = form.save(commit=False)
                payment.invoice = invoice
                payment.recorded_by = request.user
                payment.save()
                
                messages.success(
                    request,
                    f'Payment of ₦{payment.amount:,.2f} recorded successfully.'
                )
        else:
            messages.error(
                request,
                'Error recording payment. Please check the form.'
            )
    
    return redirect('billing:invoice_detail', pk=invoice.pk)


# ==========================================
# PDF GENERATION VIEWS
# ==========================================

@login_required
def generate_invoice_pdf_view(request, invoice_pk):
    """Generate and download invoice PDF"""
    invoice = get_object_or_404(
        Invoice.objects.select_related(
            'vendor', 'insurance_provider', 'corporate_client', 'created_by'
        ).prefetch_related('billing_records', 'payments'),
        pk=invoice_pk,
        vendor=request.user.vendor
    )
    
    # Generate PDF
    pdf_file = generate_invoice_pdf(invoice)
    
    # Return as downloadable PDF
    response = HttpResponse(pdf_file, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="invoice_{invoice.invoice_number}.pdf"'
    
    return response


@login_required
def preview_invoice_pdf_view(request, invoice_pk):
    """Preview invoice PDF in browser"""
    invoice = get_object_or_404(
        Invoice.objects.select_related(
            'vendor', 'insurance_provider', 'corporate_client', 'created_by'
        ).prefetch_related('billing_records', 'payments'),
        pk=invoice_pk,
        vendor=request.user.vendor
    )
    
    # Generate PDF
    pdf_file = generate_invoice_pdf(invoice)
    
    # Return as inline PDF (for preview)
    response = HttpResponse(pdf_file, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="invoice_{invoice.invoice_number}.pdf"'
    
    return response


@login_required
def generate_receipt_pdf_view(request, payment_pk):
    """Generate and download payment receipt PDF"""
    payment = get_object_or_404(
        InvoicePayment.objects.select_related(
            'invoice__vendor',
            'invoice__insurance_provider',
            'invoice__corporate_client',
            'recorded_by'
        ),
        pk=payment_pk,
        invoice__vendor=request.user.vendor
    )
    
    # Generate PDF
    pdf_file = generate_receipt_pdf(payment)
    
    # Return as downloadable PDF
    response = HttpResponse(pdf_file, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="receipt_{payment.invoice.invoice_number}_{payment.pk}.pdf"'
    
    return response


@login_required
def preview_receipt_pdf_view(request, payment_pk):
    """Preview payment receipt PDF in browser"""
    payment = get_object_or_404(
        InvoicePayment.objects.select_related(
            'invoice__vendor',
            'invoice__insurance_provider',
            'invoice__corporate_client',
            'recorded_by'
        ),
        pk=payment_pk,
        invoice__vendor=request.user.vendor
    )
    
    # Generate PDF
    pdf_file = generate_receipt_pdf(payment)
    
    # Return as inline PDF (for preview)
    response = HttpResponse(pdf_file, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="receipt_{payment.invoice.invoice_number}_{payment.pk}.pdf"'
    
    return response


# ==========================================
# EMAIL VIEWS
# ==========================================

@login_required
def email_invoice_view(request, invoice_pk):
    """Send invoice PDF via email"""
    invoice = get_object_or_404(
        Invoice.objects.select_related(
            'vendor', 'insurance_provider', 'corporate_client', 'created_by'
        ).prefetch_related('billing_records', 'payments'),
        pk=invoice_pk,
        vendor=request.user.vendor
    )
    
    if request.method == 'POST':
        recipient_email = request.POST.get('recipient_email', '').strip()
        cc_emails = request.POST.get('cc_emails', '').strip()
        subject = request.POST.get('subject', f'Invoice {invoice.invoice_number}')
        message = request.POST.get('message', '')
        
        if not recipient_email:
            messages.error(request, 'Please provide a recipient email address.')
            return redirect('billing:invoice_detail', pk=invoice.pk)
        
        try:
            # Generate PDF
            pdf_file = generate_invoice_pdf(invoice)
            
            # Prepare email
            email = EmailMessage(
                subject=subject,
                body=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[recipient_email],
            )
            
            # Add CC if provided
            if cc_emails:
                cc_list = [email.strip() for email in cc_emails.split(',') if email.strip()]
                email.cc = cc_list
            
            # Attach PDF
            email.attach(
                f'invoice_{invoice.invoice_number}.pdf',
                pdf_file,
                'application/pdf'
            )
            
            # Send email
            email.send()
            
            # Update invoice status if it's still draft
            if invoice.status == 'DRAFT':
                invoice.status = 'SENT'
                invoice.save(update_fields=['status', 'updated_at'])
            
            messages.success(
                request,
                f'Invoice {invoice.invoice_number} sent successfully to {recipient_email}.'
            )
            
        except Exception as e:
            messages.error(request, f'Error sending email: {str(e)}')
        
        return redirect('billing:invoice_detail', pk=invoice.pk)
    
    # GET request - show email form
    client = invoice.insurance_provider or invoice.corporate_client
    client_email = getattr(client, 'email', '') if client else ''
    
    context = {
        'invoice': invoice,
        'client_email': client_email,
        'default_subject': f'Invoice {invoice.invoice_number} from {invoice.vendor.name}',
        'default_message': render_to_string('billing/email/invoice_email_body.txt', {
            'invoice': invoice,
            'vendor': invoice.vendor,
        }),
    }
    
    return render(request, 'billing/email_invoice_form.html', context)


@login_required
def email_receipt_view(request, payment_pk):
    """Send payment receipt PDF via email"""
    payment = get_object_or_404(
        InvoicePayment.objects.select_related(
            'invoice__vendor',
            'invoice__insurance_provider',
            'invoice__corporate_client',
            'recorded_by'
        ),
        pk=payment_pk,
        invoice__vendor=request.user.vendor
    )
    
    if request.method == 'POST':
        recipient_email = request.POST.get('recipient_email', '').strip()
        cc_emails = request.POST.get('cc_emails', '').strip()
        subject = request.POST.get('subject', f'Payment Receipt for Invoice {payment.invoice.invoice_number}')
        message = request.POST.get('message', '')
        
        if not recipient_email:
            messages.error(request, 'Please provide a recipient email address.')
            return redirect('billing:invoice_detail', pk=payment.invoice.pk)
        
        try:
            # Generate PDF
            pdf_file = generate_receipt_pdf(payment)
            
            # Prepare email
            email = EmailMessage(
                subject=subject,
                body=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[recipient_email],
            )
            
            # Add CC if provided
            if cc_emails:
                cc_list = [email.strip() for email in cc_emails.split(',') if email.strip()]
                email.cc = cc_list
            
            # Attach PDF
            email.attach(
                f'receipt_{payment.invoice.invoice_number}_{payment.pk}.pdf',
                pdf_file,
                'application/pdf'
            )
            
            # Send email
            email.send()
            
            messages.success(
                request,
                f'Receipt sent successfully to {recipient_email}.'
            )
            
        except Exception as e:
            messages.error(request, f'Error sending email: {str(e)}')
        
        return redirect('billing:invoice_detail', pk=payment.invoice.pk)
    
    # GET request - show email form
    client = payment.invoice.insurance_provider or payment.invoice.corporate_client
    client_email = getattr(client, 'email', '') if client else ''
    
    context = {
        'payment': payment,
        'invoice': payment.invoice,
        'client_email': client_email,
        'default_subject': f'Payment Receipt for Invoice {payment.invoice.invoice_number}',
        'default_message': render_to_string('billing/email/receipt_email_body.txt', {
            'payment': payment,
            'invoice': payment.invoice,
            'vendor': payment.invoice.vendor,
        }),
    }
    
    return render(request, 'billing/email_receipt_form.html', context)


@login_required
def print_invoice_view(request, invoice_pk):
    """Display print-friendly invoice view"""
    invoice = get_object_or_404(
        Invoice.objects.select_related(
            'vendor', 'insurance_provider', 'corporate_client', 'created_by'
        ).prefetch_related('billing_records', 'payments'),
        pk=invoice_pk,
        vendor=request.user.vendor
    )
    
    context = {
        'invoice': invoice,
        'balance_due': invoice.balance_due(),
    }
    
    return render(request, 'billing/invoice_print.html', context)



# # ==========================================
# # PDF GENERATION VIEWS
# # ==========================================

# class GenerateInvoicePDFView(LoginRequiredMixin, View):
#     """Generate and download invoice PDF"""
    
#     def get(self, request, invoice_pk):
#         invoice = get_object_or_404(
#             Invoice,
#             pk=invoice_pk,
#             vendor=request.user.vendor
#         )
        
#         pdf = generate_invoice_pdf(invoice)
        
#         response = HttpResponse(pdf, content_type='application/pdf')
#         response['Content-Disposition'] = f'attachment; filename="invoice_{invoice.invoice_number}.pdf"'
        
#         return response


# class GenerateReceiptPDFView(LoginRequiredMixin, View):
#     """Generate and download payment receipt PDF"""
    
#     def get(self, request, payment_pk):
#         payment = get_object_or_404(
#             Payment,
#             pk=payment_pk,
#             billing__vendor=request.user.vendor
#         )
        
#         pdf = generate_receipt_pdf(payment)
        
#         response = HttpResponse(pdf, content_type='application/pdf')
#         response['Content-Disposition'] = f'attachment; filename="receipt_{payment.pk}.pdf"'
        
#         return response

