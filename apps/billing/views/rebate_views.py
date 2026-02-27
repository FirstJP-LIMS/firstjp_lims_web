
"""
billing/views/rebate_views.py

Views:
  rebate_statement_view      — filter by referrer + date range, show aggregated records
  generate_settlement_view   — POST: create a RebateSettlement from selected records
  settlement_detail_view     — view a settlement, mark it APPROVED or PAID
  referrer_list_view         — CRUD list of partner hospitals

URL names:
  billing:rebate_statement
  billing:generate_settlement
  billing:settlement_detail    <uuid:pk>
  billing:referrer_list
  billing:referrer_create
"""

import logging
from datetime import date
from decimal import Decimal as D

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Sum, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from ..models import RebateRecord, RebateSettlement, Referrer
from ..forms import ReferrerForm

logger = logging.getLogger(__name__)


def _generate_statement_number(vendor, referrer) -> str:
    """RBS-{CODE}-{YEAR}-{SEQ:04d}  e.g. RBS-GHC-2026-0003"""
    year = timezone.now().year
    prefix = f"RBS-{referrer.code or referrer.name[:4].upper()}-{year}-"
    last = (
        RebateSettlement.objects
        .select_for_update()
        .filter(vendor=vendor, statement_number__startswith=prefix)
        .order_by('-statement_number')
        .first()
    )
    seq = 1
    if last:
        try:
            seq = int(last.statement_number.rsplit('-', 1)[-1]) + 1
        except (ValueError, IndexError):
            pass
    return f"{prefix}{seq:04d}"


@login_required
def rebate_statement_view(request):
    """
    Statement engine: filter unpaid RebateRecords by referrer + date range.

    GET  → show filter form + preview of unpaid records
    POST → create a RebateSettlement from selected records
    """

    vendor = getattr(request.user, 'vendor', None)
    if not vendor:
        messages.error(request, "Vendor account required.")
        return redirect('dashboard')

    # ── GET: filter + preview ─────────────────────────────────────────────
    if request.method == 'GET':
        referrers   = Referrer.objects.filter(vendor=vendor, is_active=True)
        referrer_id = request.GET.get('referrer', '').strip()
        start_str   = request.GET.get('start', '').strip()
        end_str     = request.GET.get('end', '').strip()

        records          = RebateRecord.objects.none()
        selected_referrer = None
        summary          = None
        start_date = end_date = None

        if referrer_id and start_str and end_str:
            try:
                start_date = date.fromisoformat(start_str)
                end_date   = date.fromisoformat(end_str)
            except ValueError:
                messages.error(request, "Invalid date format. Use YYYY-MM-DD.")
                return render(request, 'billing/rebate/statement.html', {
                    'referrers': referrers,
                })

            selected_referrer = get_object_or_404(
                Referrer, pk=referrer_id, vendor=vendor
            )

            records = (
                RebateRecord.objects
                .filter(
                    referrer=selected_referrer,
                    status='UNPAID',
                    earned_at__date__range=[start_date, end_date],
                )
                .select_related(
                    'billing',
                    'billing__request',
                    'billing__request__patient',
                )
                .order_by('earned_at')
            )

            agg = records.aggregate(
                total=Sum('rebate_amount'),
                count=Count('id'),
                basis_total=Sum('payment_basis'),
            )
            summary = {
                'record_count':  agg['count']       or 0,
                'total_rebate':  D(agg['total']      or 0),
                'total_basis':   D(agg['basis_total'] or 0),
            }

            if not records.exists():
                messages.info(
                    request,
                    f"No unpaid rebates found for {selected_referrer.name} "
                    f"in the selected period."
                )

        # Balance summary for all referrers (sidebar)
        referrer_balances = (
            Referrer.objects
            .filter(vendor=vendor, is_active=True)
            .annotate(
                unpaid_total=Sum(
                    'rebate_records__rebate_amount',
                    filter=Q(rebate_records__status='UNPAID')
                )
            )
        )

        return render(request, 'billing/rebate/statement_rebate1.html', {
            'referrers':          referrers,
            'referrer_balances':  referrer_balances,
            'records':            records,
            'selected_referrer':  selected_referrer,
            'summary':            summary,
            'start':              start_str,
            'end':                end_str,
        })

    # ── POST: generate settlement ─────────────────────────────────────────
    if request.method == 'POST':
        record_ids  = request.POST.getlist('record_ids')
        referrer_id = request.POST.get('referrer_id')
        start_str   = request.POST.get('start')
        end_str     = request.POST.get('end')

        if not record_ids:
            messages.error(request, "No records selected.")
            return redirect('billing:rebate_statement')

        referrer = get_object_or_404(Referrer, pk=referrer_id, vendor=vendor)

        try:
            with transaction.atomic():
                stmt_number = _generate_statement_number(vendor, referrer)

                settlement = RebateSettlement.objects.create(
                    vendor           = vendor,
                    referrer         = referrer,
                    statement_number = stmt_number,
                    period_start     = start_str,
                    period_end       = end_str,
                    created_by       = request.user,
                    status           = 'DRAFT',
                )

                # Attach records — re-validate eligibility in the same transaction
                eligible = RebateRecord.objects.filter(
                    id__in=record_ids,
                    referrer=referrer,
                    status='UNPAID',
                )
                if not eligible.exists():
                    raise ValueError("No eligible unpaid records found.")

                eligible.update(status='INCLUDED', settlement=settlement)
                settlement.recalculate_totals()

            messages.success(
                request,
                f"Statement {stmt_number} created for {referrer.name} "
                f"— ₦{settlement.total_amount:,.2f} across "
                f"{settlement.record_count} records."
            )
            return redirect('billing:settlement_detail', pk=settlement.pk)

        except ValueError as e:
            messages.error(request, str(e))
        except Exception:
            logger.exception("Settlement generation failed")
            messages.error(request, "An unexpected error occurred. Please try again.")

        return redirect('billing:rebate_statement')


@login_required
def settlement_detail_view(request, pk):
    """
    View a RebateSettlement.
    POST actions: approve, mark_paid, cancel.
    """
    from billing.models.referrer import RebateSettlement

    vendor = getattr(request.user, 'vendor', None)
    if not vendor:
        return redirect('dashboard')

    settlement = get_object_or_404(
        RebateSettlement.objects.select_related('referrer', 'created_by'),
        pk=pk, vendor=vendor,
    )
    records = settlement.rebate_records.select_related(
        'billing', 'billing__request', 'billing__request__patient'
    ).order_by('earned_at')

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'approve' and settlement.status == 'DRAFT':
            settlement.status = 'APPROVED'
            settlement.save(update_fields=['status', 'updated_at'])
            messages.success(request, f"Statement {settlement.statement_number} approved.")

        elif action == 'mark_paid' and settlement.status == 'APPROVED':
            payment_ref    = request.POST.get('payment_reference', '').strip()
            payment_method = request.POST.get('payment_method', '').strip()
            payment_date_str = request.POST.get('payment_date', '').strip()

            if not payment_ref:
                messages.error(request, "Payment reference is required.")
            else:
                try:
                    with transaction.atomic():
                        p_date = (
                            date.fromisoformat(payment_date_str)
                            if payment_date_str else timezone.now().date()
                        )
                        settlement.status           = 'PAID'
                        settlement.payment_date     = p_date
                        settlement.payment_reference = payment_ref
                        settlement.payment_method   = payment_method
                        settlement.save(update_fields=[
                            'status', 'payment_date', 'payment_reference',
                            'payment_method', 'updated_at'
                        ])
                        settlement.rebate_records.update(status='PAID')

                    messages.success(
                        request,
                        f"Settlement {settlement.statement_number} marked as PAID. "
                        f"₦{settlement.total_amount:,.2f} disbursed to {settlement.referrer.name}."
                    )
                except Exception:
                    logger.exception("Failed to mark settlement %s as paid", pk)
                    messages.error(request, "Could not record payment. Please try again.")

        elif action == 'cancel' and settlement.status in ('DRAFT', 'APPROVED'):
            with transaction.atomic():
                settlement.rebate_records.update(status='UNPAID', settlement=None)
                settlement.status = 'CANCELLED'
                settlement.save(update_fields=['status', 'updated_at'])
            messages.warning(
                request,
                f"Statement {settlement.statement_number} cancelled. "
                f"Records returned to unpaid pool."
            )

        return redirect('billing:settlement_detail', pk=pk)

    context = {
        'settlement': settlement,
        'referrer':   settlement.referrer,
        'records':    records,
        'can_approve': settlement.status == 'DRAFT',
        'can_pay':     settlement.status == 'APPROVED',
        'can_cancel':  settlement.status in ('DRAFT', 'APPROVED'),
    }
    return render(request, 'billing/rebate/settlement_detail.html', context)


# @login_required
# def referrer_list_view(request):
#     """List all referrers with their unpaid balance summary."""
#     from billing.models.referrer import Referrer
#     from django.db.models import Q

#     vendor = getattr(request.user, 'vendor', None)
#     if not vendor:
#         return redirect('dashboard')

#     referrers = (
#         Referrer.objects
#         .filter(vendor=vendor)
#         .annotate(
#             unpaid_count=Count(
#                 'rebate_records',
#                 filter=Q(rebate_records__status='UNPAID')
#             ),
#             unpaid_total=Sum(
#                 'rebate_records__rebate_amount',
#                 filter=Q(rebate_records__status='UNPAID')
#             ),
#             lifetime_earned=Sum('rebate_records__rebate_amount'),
#         )
#         .order_by('name')
#     )

#     return render(request, 'billing/rebate/referrer_list.html', {
#         'referrers': referrers,
#     })




@login_required
def referrer_list_view(request):
    """
    List all partner referrers with their live rebate metrics.
    Annotated with: unpaid_count, unpaid_total, lifetime_earned, referral_count.
    """
    vendor = getattr(request.user, 'vendor', None)
    if not vendor:
        return redirect('dashboard')

    referrers = (
        Referrer.objects
        .filter(vendor=vendor)
        .annotate(
            # referral_count=Count('billing_records', distinct=True),
            referral_count=Count('rebate_records', distinct=True),
            unpaid_count=Count(
                'rebate_records',
                filter=Q(rebate_records__status='UNPAID'),
                distinct=True,
            ),
            unpaid_total=Sum(
                'rebate_records__rebate_amount',
                filter=Q(rebate_records__status='UNPAID'),
            ),
            lifetime_earned=Sum('rebate_records__rebate_amount'),
        )
        .order_by('name')
    )

    # Overall summary for the top metrics strip
    summary = {
        'total_partners': referrers.count(),
        'active_partners': referrers.filter(is_active=True).count(),
        'total_unpaid': D(
            RebateRecord.objects.filter(
                referrer__vendor=vendor, status='UNPAID'
            ).aggregate(t=Sum('rebate_amount'))['t'] or 0
        ),
        'total_lifetime': D(
            RebateRecord.objects.filter(
                referrer__vendor=vendor
            ).aggregate(t=Sum('rebate_amount'))['t'] or 0
        ),
    }

    return render(request, 'billing/rebate/referrer_list.html', {
        'referrers': referrers,
        'summary':   summary,
    })


@login_required
def referrer_create_view(request):
    """Create a new partner referrer account."""
    vendor = getattr(request.user, 'vendor', None)
    if not vendor:
        return redirect('dashboard')

    if request.method == 'POST':
        form = ReferrerForm(request.POST, vendor=vendor)
        if form.is_valid():
            referrer = form.save(commit=False)
            referrer.vendor = vendor
            referrer.save()
            messages.success(
                request,
                f"Partner '{referrer.name}' created successfully. "
                f"They can now be selected on new test requests."
            )
            return redirect('billing:referrer_detail', pk=referrer.pk)
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = ReferrerForm()

    return render(request, 'billing/rebate/referrer_form.html', {
        'form':     form,
        'is_edit':  False,
        'title':    'Add Referral Partner',
    })


@login_required
def referrer_update_view(request, pk):
    """Edit an existing referrer account."""
    vendor = getattr(request.user, 'vendor', None)
    if not vendor:
        return redirect('dashboard')

    referrer = get_object_or_404(Referrer, pk=pk, vendor=vendor)

    if request.method == 'POST':
        form = ReferrerForm(request.POST, instance=referrer)
        if form.is_valid():
            form.save()
            messages.success(request, f"Partner '{referrer.name}' updated.")
            return redirect('billing:referrer_detail', pk=referrer.pk)
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = ReferrerForm(instance=referrer)

    return render(request, 'billing/rebate/referrer_form.html', {
        'form':     form,
        'referrer': referrer,
        'is_edit':  True,
        'title':    f'Edit — {referrer.name}',
    })


@login_required
def referrer_detail_view(request, pk):
    """
    Partner detail page showing:
     - Agreement terms
     - Rebate performance metrics
     - Recent billing records tagged to this referrer
     - Settlement history
    """
    vendor = getattr(request.user, 'vendor', None)
    if not vendor:
        return redirect('dashboard')

    referrer = get_object_or_404(Referrer, pk=pk, vendor=vendor)

    # Financial metrics
    rebate_agg = RebateRecord.objects.filter(referrer=referrer).aggregate(
        unpaid_total=Sum('rebate_amount', filter=Q(status='UNPAID')),
        paid_total=Sum('rebate_amount',   filter=Q(status='PAID')),
        lifetime=Sum('rebate_amount'),
        record_count=Count('id'),
    )
    metrics = {
        'unpaid_total':   D(rebate_agg['unpaid_total']  or 0),
        'paid_total':     D(rebate_agg['paid_total']    or 0),
        'lifetime':       D(rebate_agg['lifetime']      or 0),
        'record_count':   rebate_agg['record_count']    or 0,
        'referral_count': referrer.rebate_records.count(),
    }

    # Recent rebate records (latest 20)
    recent_rebates = (
        RebateRecord.objects
        .filter(referrer=referrer)
        .select_related('billing', 'billing__request', 'billing__request__patient')
        .order_by('-earned_at')[:20]
    )

    # Settlement history
    settlements = (
        RebateSettlement.objects
        .filter(referrer=referrer)
        .order_by('-created_at')[:10]
    )

    context = {
        'referrer':       referrer,
        'metrics':        metrics,
        'recent_rebates': recent_rebates,
        'settlements':    settlements,
    }
    return render(request, 'billing/rebate/referrer_detail.html', context)

