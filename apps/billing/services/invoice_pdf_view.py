import io
from decimal import Decimal

from django.utils import timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable, Paragraph, SimpleDocTemplate,
    Spacer, Table, TableStyle,
)


"""

PDF builders for:
  - build_invoice_pdf(invoice)   → Invoice PDF (existing, unchanged)
  - build_receipt_pdf(payment)   → Payment Receipt PDF (new)

Both return raw bytes and are called by:
  - The download views (streamed as HTTP response)
  - The email service (attached to email)

Install:  pip install reportlab
"""


D = Decimal
PAGE_WIDTH = A4[0]

# ── Shared palette ──────────────────────────────────
BLUE       = colors.HexColor('#2563eb')
DARK       = colors.HexColor('#111827')
MUTED      = colors.HexColor('#6b7280')
SUCCESS    = colors.HexColor('#16a34a')
LIGHT_GREY = colors.HexColor('#f9fafb')
WHITE      = colors.white
BORDER     = colors.HexColor('#e5e7eb')


# ---- Style ----------------------
def _styles():
    base = getSampleStyleSheet()
    return {
        'h1': ParagraphStyle('h1', parent=base['Normal'],
                             fontSize=20, leading=24, textColor=DARK,
                             fontName='Helvetica-Bold'),
        'h2': ParagraphStyle('h2', parent=base['Normal'],
                             fontSize=13, leading=17, textColor=DARK,
                             fontName='Helvetica-Bold'),
        'label': ParagraphStyle('label', parent=base['Normal'],
                                fontSize=7, leading=10, textColor=MUTED,
                                fontName='Helvetica-Bold',
                                spaceAfter=1),
        'val': ParagraphStyle('val', parent=base['Normal'],
                              fontSize=9, leading=13, textColor=DARK),
        'val_r': ParagraphStyle('val_r', parent=base['Normal'],
                                fontSize=9, leading=13, textColor=DARK,
                                alignment=2),
        'bold': ParagraphStyle('bold', parent=base['Normal'],
                               fontSize=9, leading=13, textColor=DARK,
                               fontName='Helvetica-Bold'),
        'bold_r': ParagraphStyle('bold_r', parent=base['Normal'],
                                 fontSize=9, leading=13, textColor=DARK,
                                 fontName='Helvetica-Bold', alignment=2),
        'mono': ParagraphStyle('mono', parent=base['Normal'],
                               fontSize=9, leading=13, textColor=DARK,
                               fontName='Courier'),
        'mono_r': ParagraphStyle('mono_r', parent=base['Normal'],
                                 fontSize=9, leading=13, textColor=DARK,
                                 fontName='Courier', alignment=2),
        'th': ParagraphStyle('th', parent=base['Normal'],
                             fontSize=7, leading=10, textColor=WHITE,
                             fontName='Helvetica-Bold'),
        'th_r': ParagraphStyle('th_r', parent=base['Normal'],
                               fontSize=7, leading=10, textColor=WHITE,
                               fontName='Helvetica-Bold', alignment=2),
        'td': ParagraphStyle('td', parent=base['Normal'],
                             fontSize=8, leading=12, textColor=DARK),
        'td_r': ParagraphStyle('td_r', parent=base['Normal'],
                               fontSize=8, leading=12, textColor=DARK,
                               alignment=2),
        'footer': ParagraphStyle('footer', parent=base['Normal'],
                                 fontSize=7, leading=10, textColor=MUTED,
                                 alignment=1),
        'amount': ParagraphStyle('amount', parent=base['Normal'],
                                 fontSize=14, leading=18, textColor=SUCCESS,
                                 fontName='Helvetica-Bold', alignment=2),
    }


# Currency -----------
def _ngn(amount) -> str:
    """Format Decimal as NGN X,XXX.XX (avoids ₦ glyph which breaks built-in fonts)."""
    return f"NGN {D(amount):,.2f}"


def _header_table(W, S, vendor, right_lines: list) -> Table:
    """
    Two-column header: vendor name (left) / document title + ref (right).
    right_lines = list of Paragraph objects.
    """
    data = [
        [Paragraph(getattr(vendor, 'name', 'Laboratory'), S['h1']),
         right_lines[0]],
    ]
    for line in right_lines[1:]:
        data.append([Paragraph('', S['val']), line])

    t = Table(data, colWidths=[W * 0.55, W * 0.45])
    t.setStyle(TableStyle([
        ('ALIGN',   (1, 0), (1, -1), 'RIGHT'),
        ('VALIGN',  (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    return t


def _meta_grid(W, S, cells) -> Table:
    """
    Horizontal meta strip.
    cells = list of (label_str, value_str)
    """
    col_w = W / len(cells)
    label_row = [Paragraph(c[0].upper(), S['label']) for c in cells]
    val_row   = [Paragraph(c[1], S['val'])            for c in cells]
    t = Table([label_row, val_row], colWidths=[col_w] * len(cells))
    t.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), LIGHT_GREY),
        ('BOX',           (0, 0), (-1, -1), 0.5, BORDER),
        ('INNERGRID',     (0, 0), (-1, -1), 0.5, BORDER),
        ('TOPPADDING',    (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ('LEFTPADDING',   (0, 0), (-1, -1), 10),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 10),
    ]))
    return t


def _two_col(W, S, left_paras, right_paras) -> Table:
    """Two-column block — provider address left, data right."""
    left_cell  = left_paras
    right_cell = right_paras
    t = Table([[left_cell, right_cell]], colWidths=[W * 0.5, W * 0.5])
    t.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING',  (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    return t


# ──────────────────────────────
# Invoice PDF
# ─────────────────────────────

def build_invoice_pdf(invoice) -> bytes:
    """Return PDF bytes for an Invoice."""
    buf = io.BytesIO()
    W   = PAGE_WIDTH - 40 * mm
    S   = _styles()
    vendor   = invoice.vendor
    provider = invoice.insurance_provider

    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=20*mm, rightMargin=20*mm,
        topMargin=20*mm, bottomMargin=20*mm,
        title=f"Invoice {invoice.invoice_number}",
    )
    story = []

    # Header
    story.append(_header_table(W, S, vendor, [
        Paragraph('INVOICE', S['h1']),
        Paragraph(invoice.invoice_number, S['mono']),
    ]))
    story.append(HRFlowable(width=W, thickness=1.5, color=BLUE, spaceAfter=8))

    # Meta strip
    story.append(_meta_grid(W, S, [
        ('Invoice Date', invoice.invoice_date.strftime('%d %b %Y')),
        ('Due Date',     invoice.due_date.strftime('%d %b %Y')),
        ('Period',       f"{invoice.period_start.strftime('%d %b')} – {invoice.period_end.strftime('%d %b %Y')}"),
        ('Status',       invoice.get_status_display()),
        ('Payment Terms', f"{provider.payment_terms_days} days" if provider else '—'),
    ]))
    story.append(Spacer(1, 6*mm))

    # Bill To / Invoice summary two-col
    bill_to = [
        Paragraph('BILL TO', S['label']),
        Paragraph(provider.name if provider else '—', S['bold']),
    ]
    if provider:
        for line in [provider.address, provider.contact_person, provider.email]:
            if line:
                bill_to.append(Paragraph(line, S['val']))

    inv_summary = [
        Paragraph('AMOUNT DUE', S['label']),
        Paragraph(_ngn(invoice.total_amount), S['amount']),
        Spacer(1, 4),
        Paragraph(f"Amount Paid:   {_ngn(invoice.amount_paid)}", S['val']),
        Paragraph(f"Balance Due:   {_ngn(invoice.balance_due())}", S['bold']),
    ]

    story.append(_two_col(W, S, bill_to, inv_summary))
    story.append(Spacer(1, 8*mm))
    story.append(HRFlowable(width=W, thickness=0.5, color=BORDER, spaceAfter=4))

    # Line items
    line_items = (
        invoice.billing_records
        .select_related('request', 'request__patient')
        .order_by('created_at')
    )
    col_w = [W*0.14, W*0.26, W*0.12, W*0.16, W*0.16, W*0.16]
    table_data = [[
        Paragraph('Request',   S['th']),
        Paragraph('Patient',   S['th']),
        Paragraph('Date',      S['th']),
        Paragraph('Contract',  S['th_r']),
        Paragraph('Pt Portion',S['th_r']),
        Paragraph('Insurance', S['th_r']),
    ]]
    for rec in line_items:
        table_data.append([
            Paragraph(str(rec.request.request_id), S['td']),
            Paragraph(rec.request.patient.get_full_name, S['td']),
            Paragraph(rec.created_at.strftime('%d %b %Y'), S['td']),
            Paragraph(_ngn(rec.total_amount),      S['td_r']),
            Paragraph(_ngn(rec.patient_portion),   S['td_r']),
            Paragraph(_ngn(rec.insurance_portion), S['td_r']),
        ])

    lt = Table(table_data, colWidths=col_w, repeatRows=1)
    lt.setStyle(TableStyle([
        ('BACKGROUND',     (0, 0), (-1, 0), DARK),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [WHITE, LIGHT_GREY]),
        ('GRID',           (0, 0), (-1, -1), 0.4, BORDER),
        ('TOPPADDING',     (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING',  (0, 0), (-1, -1), 5),
        ('LEFTPADDING',    (0, 0), (-1, -1), 6),
        ('RIGHTPADDING',   (0, 0), (-1, -1), 6),
    ]))
    story.append(lt)
    story.append(Spacer(1, 6*mm))

    # Totals
    totals = Table([
        [Paragraph('Insurance Payable:', S['bold']),
         Paragraph(_ngn(invoice.total_amount), S['bold_r'])],
        [Paragraph('Amount Received:',  S['val']),
         Paragraph(_ngn(invoice.amount_paid), S['val_r'])],
        [Paragraph('Balance Due:',      S['bold']),
         Paragraph(_ngn(invoice.balance_due()), S['amount'])],
    ], colWidths=[W*0.7, W*0.3], hAlign='RIGHT')
    totals.setStyle(TableStyle([
        ('LINEABOVE',     (0, 2), (-1, 2), 1, DARK),
        ('TOPPADDING',    (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(totals)

    if invoice.notes:
        story.append(Spacer(1, 6*mm))
        story.append(HRFlowable(width=W, thickness=0.4, color=MUTED))
        story.append(Spacer(1, 3*mm))
        story.append(Paragraph('NOTES', S['label']))
        story.append(Paragraph(invoice.notes, S['val']))

    story.append(Spacer(1, 10*mm))
    story.append(HRFlowable(width=W, thickness=0.4, color=BORDER))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph(
        f"Generated {timezone.now().strftime('%d %b %Y %H:%M')} · "
        f"{invoice.invoice_number} · "
        f"Quote invoice number with all payments.",
        S['footer'],
    ))
    story.append(Spacer(1, 10*mm))
    story.append(HRFlowable(width=W, thickness=0.4, color=BORDER))
    story.append(Paragraph("Powered by MEDVUNO.",))

    doc.build(story)
    return buf.getvalue()


# ───────────────────────────────
# Receipt PDF
# ───────────────────────────────

def build_receipt_pdf(payment) -> bytes:
    """
    Return PDF bytes for an InvoicePayment receipt.

    Layout:
      Header (lab name / RECEIPT)
      ──────────────────────────
      Meta strip: Receipt No · Date · Method · Reference
      ──────────────────────────
      Received From / Payment Summary (two-col)
      ──────────────────────────
      Invoice line breakdown (compact)
      ──────────────────────────
      Remaining balance
      Footer
    """
    buf      = io.BytesIO()
    W        = PAGE_WIDTH - 40 * mm
    S        = _styles()
    invoice  = payment.invoice
    vendor   = invoice.vendor
    provider = invoice.insurance_provider

    # Receipt number: use last 8 chars of payment UUID for brevity
    receipt_no = f"RCP-{str(payment.pk).replace('-','').upper()[:8]}"

    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=20*mm, rightMargin=20*mm,
        topMargin=20*mm, bottomMargin=20*mm,
        title=f"Receipt {receipt_no}",
    )
    story = []

    # ── Header ───────────────────────────────────────────────────────────
    story.append(_header_table(W, S, vendor, [
        Paragraph('PAYMENT RECEIPT', S['h1']),
        Paragraph(receipt_no, S['mono']),
    ]))
    story.append(HRFlowable(width=W, thickness=1.5, color=SUCCESS, spaceAfter=8))

    # ── Meta strip ────────────────────────────────────────────────────────
    story.append(_meta_grid(W, S, [
        ('Receipt No',      receipt_no),
        ('Payment Date',    payment.payment_date.strftime('%d %b %Y')),
        ('Method',          payment.get_payment_method_display()),
        ('Reference',       payment.reference_number or '—'),
        ('Invoice',         invoice.invoice_number),
    ]))
    story.append(Spacer(1, 6*mm))

    # ── Received From / Amount two-col ────────────────────────────────────
    received_from = [
        Paragraph('RECEIVED FROM', S['label']),
        Paragraph(provider.name if provider else '—', S['bold']),
    ]
    if provider:
        for line in [provider.contact_person, provider.email]:
            if line:
                received_from.append(Paragraph(line, S['val']))

    amount_section = [
        Paragraph('AMOUNT RECEIVED', S['label']),
        Paragraph(_ngn(payment.amount), S['amount']),
    ]

    story.append(_two_col(W, S, received_from, amount_section))
    story.append(Spacer(1, 8*mm))
    story.append(HRFlowable(width=W, thickness=0.5, color=BORDER, spaceAfter=4))

    # ── Invoice context ───────────────────────────────────────────────────
    story.append(Paragraph('AGAINST INVOICE', S['label']))
    story.append(Spacer(1, 2*mm))

    inv_data = [
        [Paragraph('Field',         S['th']),
         Paragraph('Value',         S['th_r'])],
        [Paragraph('Invoice Number',S['td']),
         Paragraph(invoice.invoice_number, S['td_r'])],
        [Paragraph('Invoice Total', S['td']),
         Paragraph(_ngn(invoice.total_amount), S['td_r'])],
        [Paragraph('This Payment',  S['td']),
         Paragraph(_ngn(payment.amount), S['td_r'])],
        [Paragraph('Remaining Balance', S['bold']),
         Paragraph(_ngn(invoice.balance_due()), S['bold_r'])],
    ]
    inv_table = Table(inv_data, colWidths=[W*0.6, W*0.4])
    inv_table.setStyle(TableStyle([
        ('BACKGROUND',     (0, 0), (-1, 0), DARK),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [WHITE, LIGHT_GREY]),
        ('LINEBELOW',      (0, -2), (-1, -2), 1, DARK),
        ('GRID',           (0, 0), (-1, -1), 0.4, BORDER),
        ('TOPPADDING',     (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING',  (0, 0), (-1, -1), 6),
        ('LEFTPADDING',    (0, 0), (-1, -1), 8),
        ('RIGHTPADDING',   (0, 0), (-1, -1), 8),
    ]))
    story.append(inv_table)

    # ── Balance status message ────────────────────────────────────────────
    story.append(Spacer(1, 6*mm))
    balance = invoice.balance_due()
    if balance <= 0:
        msg = "This invoice is now FULLY PAID. Thank you."
        msg_style = ParagraphStyle(
            'msg_paid', parent=S['bold'],
            textColor=SUCCESS, alignment=1, fontSize=10,
        )
    else:
        msg = f"Remaining balance of {_ngn(balance)} is due by {invoice.due_date.strftime('%d %b %Y')}."
        msg_style = ParagraphStyle(
            'msg_bal', parent=S['val'],
            textColor=MUTED, alignment=1,
        )
    bal_box = Table([[Paragraph(msg, msg_style)]],
                    colWidths=[W])
    bal_box.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), LIGHT_GREY),
        ('BOX',           (0, 0), (-1, -1), 0.5, BORDER),
        ('TOPPADDING',    (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
    ]))
    story.append(bal_box)

    if payment.notes:
        story.append(Spacer(1, 6*mm))
        story.append(Paragraph('NOTES', S['label']))
        story.append(Paragraph(payment.notes, S['val']))

    # ── Footer ────────────────────────────────────────────────────────────
    story.append(Spacer(1, 10*mm))
    story.append(HRFlowable(width=W, thickness=0.4, color=BORDER))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph(
        f"Receipt generated {timezone.now().strftime('%d %b %Y %H:%M')} · "
        f"{receipt_no} · "
        f"Recorded by {getattr(payment.recorded_by, 'get_full_name', lambda: str(payment.recorded_by))()}.",
        S['footer'],
    ))
    story.append(Spacer(1, 10*mm))
    story.append(HRFlowable(width=W, thickness=0.4, color=BORDER))
    story.append(Paragraph("Powered by MEDVUNO.",))

    doc.build(story)
    return buf.getvalue()


