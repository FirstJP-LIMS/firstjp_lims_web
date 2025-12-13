"""
PDF generation utilities using WeasyPrint
Place this in: billing/utils.py
"""

from django.template.loader import render_to_string
from weasyprint import HTML, CSS
from weasyprint.text.fonts import FontConfiguration
import io


def generate_invoice_pdf(invoice):
    """
    Generate PDF for invoice using WeasyPrint
    
    Args:
        invoice: Invoice model instance
        
    Returns:
        bytes: PDF file content
    """
    # Prepare context data
    context = {
        'invoice': invoice,
        'vendor': invoice.vendor,
        'client': invoice.insurance_provider or invoice.corporate_client,
        'billing_records': invoice.billing_records.all().select_related(
            'appointment__patient',
            'service'
        ),
        'payments': invoice.payments.all(),
        'balance_due': invoice.balance_due(),
    }
    
    # Render HTML template
    html_string = render_to_string('billing/pdf/invoice_pdf.html', context)
    
    # Configure fonts
    font_config = FontConfiguration()
    
    # CSS for styling
    css_string = CSS(string='''
        @page {
            size: A4;
            margin: 1cm;
        }
        body {
            font-family: Arial, sans-serif;
            font-size: 10pt;
            line-height: 1.4;
        }
        .header {
            margin-bottom: 20px;
        }
        .invoice-details {
            margin-bottom: 20px;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 20px;
        }
        th, td {
            padding: 8px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }
        th {
            background-color: #f2f2f2;
            font-weight: bold;
        }
        .text-right {
            text-align: right;
        }
        .total-section {
            margin-top: 20px;
            float: right;
            width: 40%;
        }
        .total-row {
            display: flex;
            justify-content: space-between;
            padding: 5px 0;
        }
        .total-row.grand-total {
            font-weight: bold;
            font-size: 12pt;
            border-top: 2px solid #333;
            padding-top: 10px;
        }
        .footer {
            margin-top: 40px;
            clear: both;
            border-top: 1px solid #ddd;
            padding-top: 10px;
            font-size: 9pt;
            color: #666;
        }
    ''', font_config=font_config)
    
    # Generate PDF
    html = HTML(string=html_string)
    pdf_file = html.write_pdf(stylesheets=[css_string], font_config=font_config)
    
    return pdf_file


def generate_receipt_pdf(payment):
    """
    Generate PDF for payment receipt using WeasyPrint
    
    Args:
        payment: InvoicePayment model instance
        
    Returns:
        bytes: PDF file content
    """
    invoice = payment.invoice
    
    # Prepare context data
    context = {
        'payment': payment,
        'invoice': invoice,
        'vendor': invoice.vendor,
        'client': invoice.insurance_provider or invoice.corporate_client,
        'balance_due': invoice.balance_due(),
    }
    
    # Render HTML template
    html_string = render_to_string('billing/pdf/receipt_pdf.html', context)
    
    # Configure fonts
    font_config = FontConfiguration()
    
    # CSS for styling
    css_string = CSS(string='''
        @page {
            size: A4;
            margin: 1cm;
        }
        body {
            font-family: Arial, sans-serif;
            font-size: 10pt;
            line-height: 1.4;
        }
        .header {
            margin-bottom: 20px;
            text-align: center;
        }
        .receipt-title {
            font-size: 18pt;
            font-weight: bold;
            margin-bottom: 10px;
        }
        .receipt-details {
            margin: 20px 0;
        }
        .detail-row {
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid #eee;
        }
        .detail-label {
            font-weight: bold;
            width: 40%;
        }
        .detail-value {
            width: 60%;
        }
        .amount-section {
            margin: 30px 0;
            padding: 20px;
            background-color: #f9f9f9;
            border: 2px solid #333;
        }
        .amount-paid {
            font-size: 16pt;
            font-weight: bold;
            text-align: center;
        }
        .footer {
            margin-top: 40px;
            border-top: 1px solid #ddd;
            padding-top: 10px;
            font-size: 9pt;
            color: #666;
            text-align: center;
        }
    ''', font_config=font_config)
    
    # Generate PDF
    html = HTML(string=html_string)
    pdf_file = html.write_pdf(stylesheets=[css_string], font_config=font_config)
    
    return pdf_file
