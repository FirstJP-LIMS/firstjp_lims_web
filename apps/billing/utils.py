from decimal import Decimal
from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
)
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from django.utils import timezone
from datetime import timedelta
from django.conf import settings
import os


def generate_invoice_pdf(invoice):
    """
    Generate a professional invoice PDF
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=30, leftMargin=30,
                           topMargin=30, bottomMargin=18)
    
    elements = []
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#1a365d'),
        spaceAfter=30,
        alignment=TA_CENTER
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.HexColor('#2d3748'),
        spaceAfter=12,
        spaceBefore=12
    )
    
    # Header - Company Logo and Info
    vendor = invoice.vendor
    
    # Title
    elements.append(Paragraph("INVOICE", title_style))
    elements.append(Spacer(1, 12))
    
    # Company and Client Info Table
    info_data = [
        [Paragraph(f"<b>{vendor.name}</b>", styles['Normal']),
         '',
         Paragraph(f"<b>Invoice #:</b> {invoice.invoice_number}", styles['Normal'])],
        [Paragraph(f"{vendor.address if hasattr(vendor, 'address') else ''}", styles['Normal']),
         '',
         Paragraph(f"<b>Date:</b> {invoice.invoice_date.strftime('%d %b %Y')}", styles['Normal'])],
        [Paragraph(f"Phone: {vendor.phone if hasattr(vendor, 'phone') else ''}", styles['Normal']),
         '',
         Paragraph(f"<b>Due Date:</b> {invoice.due_date.strftime('%d %b %Y')}", styles['Normal'])],
    ]
    
    info_table = Table(info_data, colWidths=[3*inch, 1*inch, 2.5*inch])
    info_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 20))
    
    # Bill To Section
    elements.append(Paragraph("BILL TO", heading_style))
    
    client = invoice.insurance_provider or invoice.corporate_client
    client_name = client.name if invoice.insurance_provider else client.company_name
    
    bill_to_data = [
        [Paragraph(f"<b>{client_name}</b>", styles['Normal'])],
    ]
    
    if invoice.insurance_provider:
        bill_to_data.append([Paragraph(f"{client.contact_person}", styles['Normal'])])
        bill_to_data.append([Paragraph(f"{client.email}", styles['Normal'])])
        bill_to_data.append([Paragraph(f"{client.phone}", styles['Normal'])])
    else:
        bill_to_data.append([Paragraph(f"{client.contact_person}", styles['Normal'])])
        bill_to_data.append([Paragraph(f"{client.email}", styles['Normal'])])
        bill_to_data.append([Paragraph(f"{client.billing_address}", styles['Normal'])])
    
    bill_table = Table(bill_to_data, colWidths=[6*inch])
    bill_table.setStyle(TableStyle([
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(bill_table)
    elements.append(Spacer(1, 20))
    
    # Invoice Period
    elements.append(Paragraph(
        f"<b>Billing Period:</b> {invoice.period_start.strftime('%d %b %Y')} to {invoice.period_end.strftime('%d %b %Y')}",
        styles['Normal']
    ))
    elements.append(Spacer(1, 20))
    
    # Line Items Table
    elements.append(Paragraph("INVOICE DETAILS", heading_style))
    
    # Table headers
    line_items_data = [
        [Paragraph('<b>Request ID</b>', styles['Normal']),
         Paragraph('<b>Patient Name</b>', styles['Normal']),
         Paragraph('<b>Date</b>', styles['Normal']),
         Paragraph('<b>Tests</b>', styles['Normal']),
         Paragraph('<b>Amount (₦)</b>', styles['Normal'])]
    ]
    
    # Add billing records
    for billing in invoice.billing_records.all():
        request = billing.request
        patient_name = f"{request.patient.first_name} {request.patient.last_name}" if hasattr(request, 'patient') else "N/A"
        
        # Get test names
        test_names = ", ".join([
            assignment.test.name 
            for assignment in request.test_assignments.all()[:3]
        ])
        if request.test_assignments.count() > 3:
            test_names += f" (+{request.test_assignments.count() - 3} more)"
        
        line_items_data.append([
            Paragraph(str(request.request_id), styles['Normal']),
            Paragraph(patient_name, styles['Normal']),
            Paragraph(billing.created_at.strftime('%d %b'), styles['Normal']),
            Paragraph(test_names, styles['Normal']),
            Paragraph(f"{billing.insurance_portion:,.2f}", styles['Normal'])
        ])
    
    # Add totals
    line_items_data.extend([
        ['', '', '', Paragraph('<b>Subtotal:</b>', styles['Normal']), 
         Paragraph(f"<b>{invoice.subtotal:,.2f}</b>", styles['Normal'])],
        ['', '', '', Paragraph('<b>Tax:</b>', styles['Normal']), 
         Paragraph(f"<b>{invoice.tax:,.2f}</b>", styles['Normal'])],
        ['', '', '', Paragraph('<b>Total Amount:</b>', styles['Normal']), 
         Paragraph(f"<b>{invoice.total_amount:,.2f}</b>", styles['Normal'])],
        ['', '', '', Paragraph('<b>Amount Paid:</b>', styles['Normal']), 
         Paragraph(f"<b>{invoice.amount_paid:,.2f}</b>", styles['Normal'])],
        ['', '', '', Paragraph('<b>Balance Due:</b>', styles['Normal']), 
         Paragraph(f"<b>{invoice.balance_due():,.2f}</b>", styles['Normal'])],
    ])
    
    line_items_table = Table(line_items_data, colWidths=[1.2*inch, 1.8*inch, 0.8*inch, 2*inch, 1.2*inch])
    line_items_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2d3748')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('TOPPADDING', (0, 0), (-1, 0), 12),
        ('GRID', (0, 0), (-1, -6), 1, colors.grey),
        ('ALIGN', (-1, 1), (-1, -1), 'RIGHT'),
        ('LINEABOVE', (3, -5), (-1, -5), 1, colors.black),
        ('LINEABOVE', (3, -1), (-1, -1), 2, colors.black),
        ('BACKGROUND', (3, -1), (-1, -1), colors.HexColor('#edf2f7')),
    ]))
    
    elements.append(line_items_table)
    elements.append(Spacer(1, 30))
    
    # Payment Terms
    if invoice.notes:
        elements.append(Paragraph("<b>Notes:</b>", styles['Normal']))
        elements.append(Paragraph(invoice.notes, styles['Normal']))
        elements.append(Spacer(1, 12))
    
    # Footer
    payment_terms_style = ParagraphStyle(
        'PaymentTerms',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.HexColor('#4a5568')
    )
    
    payment_terms = f"""
    <b>Payment Terms:</b> Payment is due within {client.payment_terms_days} days from invoice date.<br/>
    <b>Bank Details:</b> {vendor.bank_name if hasattr(vendor, 'bank_name') else 'Contact for details'}<br/>
    <b>Account Number:</b> {vendor.account_number if hasattr(vendor, 'account_number') else 'Contact for details'}
    """
    
    elements.append(Paragraph(payment_terms, payment_terms_style))
    elements.append(Spacer(1, 20))
    
    # Thank you message
    thank_you_style = ParagraphStyle(
        'ThankYou',
        parent=styles['Normal'],
        fontSize=10,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#2d3748')
    )
    elements.append(Paragraph("<b>Thank you for your business!</b>", thank_you_style))
    
    # Build PDF
    doc.build(elements)
    
    pdf = buffer.getvalue()
    buffer.close()
    
    return pdf


def generate_receipt_pdf(payment):
    """
    Generate a payment receipt PDF
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=30, leftMargin=30,
                           topMargin=30, bottomMargin=18)
    
    elements = []
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#1a365d'),
        spaceAfter=30,
        alignment=TA_CENTER
    )
    
    # Title
    elements.append(Paragraph("PAYMENT RECEIPT", title_style))
    elements.append(Spacer(1, 12))
    
    # Receipt Info
    billing = payment.billing
    vendor = billing.vendor
    
    receipt_data = [
        [Paragraph(f"<b>{vendor.name}</b>", styles['Normal']), '',
         Paragraph(f"<b>Receipt #:</b> REC-{payment.pk:06d}", styles['Normal'])],
        [Paragraph(f"{vendor.address if hasattr(vendor, 'address') else ''}", styles['Normal']), '',
         Paragraph(f"<b>Date:</b> {payment.payment_date.strftime('%d %b %Y %H:%M')}", styles['Normal'])],
        [Paragraph(f"Phone: {vendor.phone if hasattr(vendor, 'phone') else ''}", styles['Normal']), '',
         Paragraph(f"<b>Payment Method:</b> {payment.get_payment_method_display()}", styles['Normal'])],
    ]
    
    receipt_table = Table(receipt_data, colWidths=[3*inch, 1*inch, 2.5*inch])
    receipt_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
    ]))
    elements.append(receipt_table)
    elements.append(Spacer(1, 30))
    
    # Patient/Client Info
    request = billing.request
    if hasattr(request, 'patient'):
        patient_name = f"{request.patient.first_name} {request.patient.last_name}"
        elements.append(Paragraph(f"<b>Received From:</b> {patient_name}", styles['Normal']))
    
    elements.append(Spacer(1, 20))
    
    # Payment Details
    payment_details_data = [
        [Paragraph('<b>Description</b>', styles['Normal']),
         Paragraph('<b>Amount (₦)</b>', styles['Normal'])],
        [Paragraph(f"Payment for {billing.billing_type} Bill - Request {request.request_id}", styles['Normal']),
         Paragraph(f"{payment.amount:,.2f}", styles['Normal'])],
    ]
    
    payment_table = Table(payment_details_data, colWidths=[4.5*inch, 2*inch])
    payment_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2d3748')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('TOPPADDING', (0, 0), (-1, 0), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey),
        ('ALIGN', (-1, 1), (-1, -1), 'RIGHT'),
    ]))
    
    elements.append(payment_table)
    elements.append(Spacer(1, 20))
    
    # Transaction reference
    if payment.transaction_reference:
        elements.append(Paragraph(
            f"<b>Transaction Reference:</b> {payment.transaction_reference}",
            styles['Normal']
        ))
        elements.append(Spacer(1, 12))
    
    # Balance Info
    balance_due = billing.get_balance_due()
    elements.append(Paragraph(f"<b>Total Bill Amount:</b> ₦{billing.total_amount:,.2f}", styles['Normal']))
    elements.append(Paragraph(f"<b>Amount Paid:</b> ₦{payment.amount:,.2f}", styles['Normal']))
    elements.append(Paragraph(f"<b>Balance Due:</b> ₦{balance_due:,.2f}", styles['Normal']))
    
    elements.append(Spacer(1, 30))
    
    # Notes
    if payment.notes:
        elements.append(Paragraph(f"<b>Notes:</b> {payment.notes}", styles['Normal']))
        elements.append(Spacer(1, 12))
    
    # Footer
    elements.append(Spacer(1, 40))
    
    signature_data = [
        ['_______________________', '_______________________'],
        ['Received By', 'Authorized Signature'],
    ]
    
    signature_table = Table(signature_data, colWidths=[3*inch, 3*inch])
    signature_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TOPPADDING', (0, 1), (-1, 1), 6),
    ]))
    elements.append(signature_table)
    
    elements.append(Spacer(1, 20))
    
    # Thank you message
    thank_you_style = ParagraphStyle(
        'ThankYou',
        parent=styles['Normal'],
        fontSize=10,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#2d3748')
    )
    elements.append(Paragraph("<b>Thank you for your payment!</b>", thank_you_style))
    elements.append(Paragraph("This is a computer-generated receipt.", thank_you_style))
    
    # Build PDF
    doc.build(elements)
    
    pdf = buffer.getvalue()
    buffer.close()
    
    return pdf


def generate_bulk_invoices(vendor, period_start, period_end, billing_type='HMO'):
    """
    Generate invoices in bulk for a period
    Returns list of created invoices
    """
    from .models import Invoice, BillingInformation
    from django.db import transaction
    
    invoices = []
    
    # Get all pending billing records
    pending_billings = BillingInformation.objects.filter(
        vendor=vendor,
        billing_type=billing_type,
        payment_status='INVOICED',
        invoices__isnull=True,
        created_at__date__range=[period_start, period_end]
    )
    
    if billing_type == 'HMO':
        # Group by insurance provider
        providers = pending_billings.values_list('insurance_provider', flat=True).distinct()
        
        for provider_id in providers:
            provider_billings = pending_billings.filter(insurance_provider_id=provider_id)
            
            if provider_billings.exists():
                with transaction.atomic():
                    invoice = Invoice.objects.create(
                        vendor=vendor,
                        insurance_provider_id=provider_id,
                        period_start=period_start,
                        period_end=period_end,
                        invoice_date=timezone.now().date(),
                        due_date=timezone.now().date() + timedelta(days=30)
                    )
                    
                    # Generate invoice number
                    invoice.invoice_number = f"INV-{timezone.now().year}-{invoice.pk:05d}"
                    invoice.save()
                    
                    # Link billing records
                    invoice.billing_records.set(provider_billings)
                    invoice.calculate_totals()
                    
                    invoices.append(invoice)
    
    elif billing_type == 'CORPORATE':
        # Group by corporate client
        clients = pending_billings.values_list('corporate_client', flat=True).distinct()
        
        for client_id in clients:
            client_billings = pending_billings.filter(corporate_client_id=client_id)
            
            if client_billings.exists():
                with transaction.atomic():
                    invoice = Invoice.objects.create(
                        vendor=vendor,
                        corporate_client_id=client_id,
                        period_start=period_start,
                        period_end=period_end,
                        invoice_date=timezone.now().date(),
                        due_date=timezone.now().date() + timedelta(days=60)
                    )
                    
                    invoice.invoice_number = f"INV-{timezone.now().year}-{invoice.pk:05d}"
                    invoice.save()
                    
                    invoice.billing_records.set(client_billings)
                    invoice.calculate_totals()
                    
                    invoices.append(invoice)
    
    return invoices