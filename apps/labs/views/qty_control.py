
"""
QUALITY CONTROL...
"""
import json
import logging
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from functools import wraps

# Django Core
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import (
    Avg, Count, DurationField, ExpressionWrapper, F, Q, Sum, Prefetch
)
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

# App-Specific Imports
from apps.accounts.models import VendorProfile
from apps.tenants.models import Vendor

from ..forms import (
    DepartmentForm,
    SampleForm,
    TestRequestForm,
    VendorLabTestForm
)
from ..models import (
    AuditLog,
    Department,
    Equipment,
    Patient,
    QualitativeOption,
    Sample,
    TestAssignment,
    TestRequest,
    TestResult,
    VendorTest
)
from ..services import (
    InstrumentAPIError,
    InstrumentService,
    fetch_assignment_result,
    send_assignment_to_instrument
)
from ..utils import check_tenant_access



from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.utils import timezone
from datetime import datetime, timedelta
from ..forms import QCLotForm, QCActionForm, QCEntryForm
from ..models import QCLot, QCAction, QCResult, QCTestApproval
import calendar
from django.db.models import Count, Q

# Logger Setup
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


# ==========================================
# QC LOT MANAGEMENT
# ==========================================

@login_required
def qc_lot_list(request):
    """List all QC lots."""
    vendor = request.user.vendor
    
    lots = QCLot.objects.filter(
        vendor=vendor
    ).select_related('test').order_by('-is_active', '-received_date')
    
    # Filter
    test_filter = request.GET.get('test')
    if test_filter:
        lots = lots.filter(test_id=test_filter)
    
    active_filter = request.GET.get('active')
    if active_filter == 'true':
        lots = lots.filter(is_active=True)
    
    tests = VendorTest.objects.filter(vendor=vendor)
    
    context = {
        'lots': lots,
        'tests': tests,
        'current_test': test_filter,
    }
    
    return render(request, 'laboratory/qc/lots/qclot_list.html', context)


@login_required
def qc_lot_create(request):
    """Create new QC lot."""
    vendor = request.user.vendor
    
    if request.method == 'POST':
        form = QCLotForm(request.POST, vendor=vendor)
        if form.is_valid():
            qc_lot = form.save(commit=False)
            qc_lot.vendor = vendor
            qc_lot.save()
            messages.success(request, f"QC Lot {qc_lot.lot_number} created successfully.")
            return redirect('labs:qclot_list')
    else:
        form = QCLotForm(vendor=vendor)
    
    return render(request, 'laboratory/qc/lots/qclot_form.html', {'form': form})


@login_required
def qc_lot_edit(request, pk):
    vendor = request.user.vendor
    qc_lot = get_object_or_404(QCLot, pk=pk, vendor=vendor)
    if request.method == 'POST':
        form = QCLotForm(vendor, request.POST, instance=qc_lot)
        if form.is_valid():
            form.save()
            messages.success(request, f'QC Lot {qc_lot} updated')
            return redirect('qc:qclot_list')
    else:
        form = QCLotForm(vendor, instance=qc_lot)
    return render(request, 'laboratory/qc/qclot_form.html', {'form': form, 'create': False, 'qclot': qc_lot})


@login_required
def qclot_toggle_active(request, pk):
    vendor = request.user.vendor
    q = get_object_or_404(QCLot, pk=pk, vendor=vendor)

    if q.is_active:
        # Deactivating
        q.is_active = False
        q.closed_date = timezone.now().date()
        q.save()
        messages.info(request, f'{q} deactivated')
    else:
        # Activating: will automatically deactivate others in model.save()
        if q.expiry_date and q.expiry_date < timezone.now().date():
            messages.error(request, 'Cannot activate an expired lot')
        else:
            q.is_active = True
            q.save()
            messages.success(request, f'{q} activated (others deactivated)')

    return redirect('labs:qclot_list')


@login_required
def qclot_delete(request, pk):
    vendor = request.user.vendor
    q = get_object_or_404(QCLot, pk=pk, vendor=vendor)
    if request.method == 'POST':
        q.delete()
        messages.success(request, 'QC Lot deleted')
        return redirect('qc:qclot_list')
    return render(request, 'laboratory/qc/qclot_confirm_delete.html', {'qclot': q})


@login_required
def qc_entry_view(request):
    vendor = request.user.vendor
    today = timezone.now().date()

    if request.method == "POST":
        form = QCEntryForm(vendor, request.POST)
        if form.is_valid():
            qc = form.save(commit=False)
            qc.vendor = vendor
            qc.entered_by = request.user

            qc.run_date = today
            qc.run_number = (
                QCResult.objects.filter(
                    vendor=vendor,
                    qc_lot=qc.qc_lot,
                    run_date=today
                ).count() + 1
            )

            qc.save()
            messages.success(request, f"QC saved — Status: {qc.status}")
            return redirect("qc_entry")
    else:
        form = QCEntryForm(vendor)

    todays_runs = QCResult.objects.filter(
        vendor=vendor,
        run_date=today
    ).select_related("qc_lot", "instrument")

    total_runs = todays_runs.count()
    passed_runs = todays_runs.filter(status="PASS").count()
    runs_with_violations = todays_runs.exclude(rule_violations=[]).count()

    context = {
        "form": form,
        "todays_runs": todays_runs,
        "total_runs": total_runs,
        "passed_runs": passed_runs,
        "runs_with_violations": runs_with_violations,
        "daily_approval_rate": round((passed_runs / total_runs * 100), 2) if total_runs else 0,
        "active_lots": QCLot.objects.filter(vendor=vendor, is_active=True).count(),
        "today": today,
    }

    return render(request, "laboratory/qc/entry/qc_entry.html", context)

# ==========================================
# LEVEY-JENNINGS CHART - Data Endpoint
# ==========================================

@login_required
def levey_jennings_data(request, qc_lot_id):
    """
    API endpoint to get data for Levey-Jennings chart.
    Returns JSON data for Chart.js.
    """
    vendor = request.user.vendor
    qc_lot = get_object_or_404(QCLot, id=qc_lot_id, vendor=vendor)
    
    # Get date range (default: last 30 days)
    days = int(request.GET.get('days', 30))
    start_date = timezone.now().date() - timedelta(days=days)
    
    # Get QC results
    results = QCResult.objects.filter(
        qc_lot=qc_lot,
        run_date__gte=start_date
    ).order_by('run_date', 'run_time')
    
    # Build chart data
    labels = []
    data_points = []
    colors = []
    
    for result in results:
        labels.append(result.run_date.strftime('%m/%d'))
        data_points.append(float(result.result_value))
        
        # Color based on status
        if result.status == 'PASS':
            colors.append('rgba(75, 192, 192, 1)')  # Green
        elif result.status == 'WARNING':
            colors.append('rgba(255, 206, 86, 1)')  # Yellow
        else:
            colors.append('rgba(255, 99, 132, 1)')  # Red
    
    # Control limits
    chart_data = {
        'labels': labels,
        'datasets': [
            {
                'label': 'QC Results',
                'data': data_points,
                'borderColor': 'rgba(54, 162, 235, 1)',
                'backgroundColor': colors,
                'pointBackgroundColor': colors,
                'pointBorderColor': colors,
                'pointRadius': 5,
                'fill': False,
            }
        ],
        'control_limits': {
            'mean': float(qc_lot.mean),
            'sd_2_high': float(qc_lot.limit_2sd_high),
            'sd_2_low': float(qc_lot.limit_2sd_low),
            'sd_3_high': float(qc_lot.limit_3sd_high),
            'sd_3_low': float(qc_lot.limit_3sd_low),
        },
        'lot_info': {
            'test': qc_lot.test.name,
            'level': qc_lot.get_level_display(),
            'lot_number': qc_lot.lot_number,
            'target': float(qc_lot.target_value),
            'units': qc_lot.units,
        }
    }
    
    return JsonResponse(chart_data)

# ==========================================
# LEVEY-JENNINGS CHART - View
# ==========================================

@login_required
def levey_jennings_chart(request, qc_lot_id=None):
    """
    Display Levey-Jennings chart for a QC lot.
    """
    vendor = request.user.vendor
    
    # Get all active QC lots for selection
    active_lots = QCLot.objects.filter(
        vendor=vendor,
        is_active=True
    ).select_related('test').order_by('test__name', 'level')
    
    qc_lot = None
    if qc_lot_id:
        qc_lot = get_object_or_404(QCLot, id=qc_lot_id, vendor=vendor)
    elif active_lots.exists():
        qc_lot = active_lots.first()
    
    context = {
        'qc_lot': qc_lot,
        'active_lots': active_lots,
    }
    return render(request, 'laboratory/qc/levey/levey_jennings.html', context)


@login_required
def qc_results_list(request):
    vendor = request.user.vendor

    results = QCResult.objects.filter(
        vendor=vendor
    ).select_related("qc_lot", "qc_lot__test", "instrument", "entered_by", "approved_by")

    # Summary stats
    total_runs = results.count()
    passed = results.filter(status='PASS').count()
    failed = results.filter(status='FAIL').count()
    warnings = results.filter(status='WARNING').count()
    approved = results.filter(is_approved=True).count()
    violations = results.filter(rule_violations__len__gt=0).count()  # if rule_violations is list-like

    # Optional: compute per-test metrics
    tests_summary = {}
    for r in results:
        if hasattr(r, 'z_score') and r.z_score is not None:
            r.z_score_abs = abs(r.z_score)
        else:
            r.z_score_abs = None

        test_code = r.qc_lot.test.code
        if test_code not in tests_summary:
            tests_summary[test_code] = {
                "test": r.qc_lot.test,
                "total": 0,
                "passed": 0,
                "failed": 0,
                "warnings": 0,
            }
        tests_summary[test_code]["total"] += 1
        if r.status == "PASS":
            tests_summary[test_code]["passed"] += 1
        elif r.status == "FAIL":
            tests_summary[test_code]["failed"] += 1
        else:
            tests_summary[test_code]["warnings"] += 1

    # Final per-test computation
    for item in tests_summary.values():
        t = item["total"]
        item["pass_rate"] = (item["passed"] / t * 100) if t else 0
        item["fail_rate"] = (item["failed"] / t * 100) if t else 0
        item["warning_rate"] = (item["warnings"] / t * 100) if t else 0

    context = {
        "results": results,
        "total_runs": total_runs,
        "passed": passed,
        "failed": failed,
        "warnings": warnings,
        "approved": approved,
        "violations": violations,
        "tests_summary": tests_summary,
    }

    return render(request, "laboratory/qc/entry/qc_results_list.html", context)


@login_required
def qc_result_detail(request, pk):
    vendor = request.user.vendor

    result = get_object_or_404(
        QCResult.objects.select_related(
            "qc_lot", "qc_lot__test", "instrument", "entered_by"
        ),
        pk=pk,
        vendor=vendor
    )

    context = {"result": result}
    return render(request, "laboratory/qc/entry/qc_result_detail.html", context)


# ==========================================
# QC REPORTS
# ==========================================

@login_required
def qc_monthly_report(request):
    """Monthly QC summary report."""
    vendor = request.user.vendor
    
    # Get month and year from request
    year = int(request.GET.get('year', timezone.now().year))
    month = int(request.GET.get('month', timezone.now().month))
    
    # Month dropdown list
    months = [
        {"num": m, "name": calendar.month_name[m]}
        for m in range(1, 13)
    ]

    # Year dropdown list (current year ± 2)
    current_year = timezone.now().year
    years = list(range(current_year - 2, current_year + 1))

    # Calculate date range
    start_date = datetime(year, month, 1).date()
    if month == 12:
        end_date = datetime(year + 1, 1, 1).date() - timedelta(days=1)
    else:
        end_date = datetime(year, month + 1, 1).date() - timedelta(days=1)
    
    # Query QC results
    results = QCResult.objects.filter(
        vendor=vendor,
        run_date__gte=start_date,
        run_date__lte=end_date
    ).select_related('qc_lot__test')
    
    total_runs = results.count()
    passed = results.filter(status='PASS').count()
    failed = results.filter(status='FAIL').count()
    warnings = results.filter(status='WARNING').count()

    # Compute overall rates
    pass_rate = (passed / total_runs * 100) if total_runs else 0
    warning_rate = (warnings / total_runs * 100) if total_runs else 0
    fail_rate = (failed / total_runs * 100) if total_runs else 0

    # Group by test + compute test-level percentages
    tests_summary = {}
    
    for result in results:
        test = result.qc_lot.test
        code = test.code
        
        if code not in tests_summary:
            tests_summary[code] = {
                "test": test,
                "total": 0,
                "passed": 0,
                "failed": 0,
                "warnings": 0,
                "pass_rate": 0,
                "warning_rate": 0,
                "fail_rate": 0,
            }
        
        tests_summary[code]["total"] += 1
        
        if result.status == "PASS":
            tests_summary[code]["passed"] += 1
        elif result.status == "FAIL":
            tests_summary[code]["failed"] += 1
        else:
            tests_summary[code]["warnings"] += 1

    # Final computation for each test + sigma conversion
    for item in tests_summary.values():
        t = item["total"]

        if t > 0:
            item["pass_rate"] = item["passed"] / t * 100
            item["warning_rate"] = item["warnings"] / t * 100
            item["fail_rate"] = item["failed"] / t * 100
            # Sigma approximation: pass rate expressed on sigma scale (0–6)
            item["sigma"] = round((item["pass_rate"] / 100) * 6, 2)
        else:
            item["pass_rate"] = 0
            item["warning_rate"] = 0
            item["fail_rate"] = 0
            item["sigma"] = 0

    overall_sigma = round((pass_rate / 100) * 6, 2)

    context = {
        "year": year,
        "month": month,
        "years": years,
        "months": months,
        "month_name": datetime(year, month, 1).strftime("%B %Y"),

        "start_date": start_date,
        "end_date": end_date,

        "total_runs": total_runs,
        "passed": passed,
        "failed": failed,
        "warnings": warnings,

        "pass_rate": round(pass_rate, 1),
        "warning_rate": round(warning_rate, 1),
        "fail_rate": round(fail_rate, 1),
        "overall_sigma": overall_sigma,
        "tests_summary": tests_summary,
    }
    
    return render(request, "laboratory/qc/metric/monthly_report.html", context)


# ==========================================
# QC DASHBOARD - Overview of QC Status
# ==========================================

@login_required
def qc_dashboard(request):
    """
    Main QC dashboard showing today's QC status for all tests.
    """
    vendor = request.user.vendor
    today = timezone.now().date()
    
    # Get all active QC lots
    active_lots = QCLot.objects.filter(
        vendor=vendor,
        is_active=True,
        expiry_date__gte=today
    ).select_related('test').order_by('test__name', 'level')
    
    # Get today's QC results
    todays_results = QCResult.objects.filter(
        vendor=vendor,
        run_date=today
    ).select_related('qc_lot', 'qc_lot__test', 'instrument')
    
    # Get test approvals for today
    test_approvals = QCTestApproval.objects.filter(
        vendor=vendor,
        date=today
    ).select_related('test')
    
    # Build summary by test
    qc_summary = {}
    for lot in active_lots:
        test_code = lot.test.code
        if test_code not in qc_summary:
            qc_summary[test_code] = {
                'test': lot.test,
                'levels': {},
                'all_passed': True,
                'any_run': False
            }
        
        # Check if this level was run today
        level_result = todays_results.filter(qc_lot=lot).first()
        qc_summary[test_code]['levels'][lot.get_level_display()] = {
            'lot': lot,
            'result': level_result,
            'status': level_result.status if level_result else 'NOT_RUN'
        }
        
        if level_result:
            qc_summary[test_code]['any_run'] = True
            if level_result.status != 'PASS':
                qc_summary[test_code]['all_passed'] = False
        else:
            qc_summary[test_code]['all_passed'] = False
    
    # Statistics
    stats = {
        'total_tests': len(qc_summary),
        'tests_approved': sum(1 for t in qc_summary.values() if t['all_passed']),
        'tests_failed': sum(1 for t in qc_summary.values() if t['any_run'] and not t['all_passed']),
        'tests_pending': sum(1 for t in qc_summary.values() if not t['any_run']),
        'total_runs_today': todays_results.count(),
    }
    
    # Recent failures (last 7 days)
    recent_failures = QCResult.objects.filter(
        vendor=vendor,
        run_date__gte=today - timedelta(days=7),
        status='FAIL'
    ).select_related('qc_lot__test')[:10]
    
    context = {
        'qc_summary': qc_summary,
        'stats': stats,
        'recent_failures': recent_failures,
        'today': today,
    }
    
    return render(request, 'laboratory/qc/qc_dashboard.html', context)


# ==========================================
# QC ACTIONS
# ==========================================

@login_required
def qc_action_create(request, result_pk):
    """
    Create corrective action for a failed QC result.
    """
    vendor = request.user.vendor
    qc_result = get_object_or_404(QCResult, pk=result_pk, vendor=vendor)
    
    # Only allow actions for failed/warning QC
    if qc_result.status == 'PASS':
        messages.warning(request, "Cannot create action for passing QC.")
        return redirect('labs:qc_result_detail', pk=result_pk)
    
    if request.method == 'POST':
        form = QCActionForm(request.POST)
        if form.is_valid():
            action = form.save(commit=False)
            action.qc_result = qc_result
            action.performed_by = request.user
            action.save()
            
            # Update QC result with corrective action taken
            if not qc_result.corrective_action:
                qc_result.corrective_action = action.description
                qc_result.save(update_fields=['corrective_action'])
            
            messages.success(request, f"Corrective action '{action.get_action_type_display()}' recorded.")
            return redirect('labs:qc_result_detail', pk=result_pk)
    else:
        form = QCActionForm()
    
    context = {
        'form': form,
        'qc_result': qc_result,
    }
    return render(request, 'laboratory/qc/actions/qc_action_form.html', context)


@login_required
def qc_action_list(request):
    """
    List all corrective actions with filtering.
    """
    vendor = request.user.vendor
    
    actions = QCAction.objects.filter(
        qc_result__vendor=vendor
    ).select_related(
        'qc_result__qc_lot__test',
        'performed_by'
    ).order_by('-performed_at')
    
    # Filters
    resolved_filter = request.GET.get('resolved')
    if resolved_filter == 'true':
        actions = actions.filter(resolved=True)
    elif resolved_filter == 'false':
        actions = actions.filter(resolved=False)
    
    action_type_filter = request.GET.get('action_type')
    if action_type_filter:
        actions = actions.filter(action_type=action_type_filter)
    
    # Statistics
    stats = {
        'total': actions.count(),
        'resolved': actions.filter(resolved=True).count(),
        'pending': actions.filter(resolved=False).count(),
    }
    
    # Action type choices for filter dropdown
    action_types = QCAction.ACTION_TYPE_CHOICES
    
    context = {
        'actions': actions,
        'stats': stats,
        'action_types': action_types,
    }
    return render(request, 'laboratory/qc/actions/qc_action_list.html', context)


@login_required
def qc_action_detail(request, pk):
    """
    View and update a single corrective action.
    """
    vendor = request.user.vendor
    action = get_object_or_404(
        QCAction.objects.select_related('qc_result__qc_lot__test', 'performed_by'),
        pk=pk,
        qc_result__vendor=vendor
    )
    
    if request.method == 'POST':
        form = QCActionForm(request.POST, instance=action)
        if form.is_valid():
            form.save()
            messages.success(request, "Action updated successfully.")
            return redirect('labs:qc_action_detail', pk=pk)
    else:
        form = QCActionForm(instance=action)
    
    # Get follow-up QC results after this action
    follow_up_results = QCResult.objects.filter(
        vendor=vendor,
        qc_lot=action.qc_result.qc_lot,
        run_date__gte=action.performed_at.date()
    ).order_by('run_date', 'run_time')[:5]
    
    context = {
        'action': action,
        'form': form,
        'follow_up_results': follow_up_results,
    }
    return render(request, 'laboratory/qc/actions/qc_action_detail.html', context)

