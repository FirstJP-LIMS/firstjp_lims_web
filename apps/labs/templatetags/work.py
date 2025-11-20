# # qc_views.py - Add to your views or create new file

# from django.shortcuts import render, redirect, get_object_or_404
# from django.contrib.auth.decorators import login_required
# from django.contrib import messages
# from django.db.models import Q, Count, Max, Min
# from django.http import JsonResponse
# from django.utils import timezone
# from datetime import timedelta, datetime
# import json

# from .models import (
#     QCLot, QCResult, QCAction, QCTestApproval,
#     VendorTest, Equipment
# )


# # ==========================================
# # QC DASHBOARD - Overview of QC Status
# # ==========================================

# @login_required
# def qc_dashboard(request):
#     """
#     Main QC dashboard showing today's QC status for all tests.
#     """
#     vendor = request.user.vendor
#     today = timezone.now().date()
    
#     # Get all active QC lots
#     active_lots = QCLot.objects.filter(
#         vendor=vendor,
#         is_active=True,
#         expiry_date__gte=today
#     ).select_related('test').order_by('test__name', 'level')
    
#     # Get today's QC results
#     todays_results = QCResult.objects.filter(
#         vendor=vendor,
#         run_date=today
#     ).select_related('qc_lot', 'qc_lot__test', 'instrument')
    
#     # Get test approvals for today
#     test_approvals = QCTestApproval.objects.filter(
#         vendor=vendor,
#         date=today
#     ).select_related('test')
    
#     # Build summary by test
#     qc_summary = {}
#     for lot in active_lots:
#         test_code = lot.test.code
#         if test_code not in qc_summary:
#             qc_summary[test_code] = {
#                 'test': lot.test,
#                 'levels': {},
#                 'all_passed': True,
#                 'any_run': False
#             }
        
#         # Check if this level was run today
#         level_result = todays_results.filter(qc_lot=lot).first()
#         qc_summary[test_code]['levels'][lot.get_level_display()] = {
#             'lot': lot,
#             'result': level_result,
#             'status': level_result.status if level_result else 'NOT_RUN'
#         }
        
#         if level_result:
#             qc_summary[test_code]['any_run'] = True
#             if level_result.status != 'PASS':
#                 qc_summary[test_code]['all_passed'] = False
#         else:
#             qc_summary[test_code]['all_passed'] = False
    
#     # Statistics
#     stats = {
#         'total_tests': len(qc_summary),
#         'tests_approved': sum(1 for t in qc_summary.values() if t['all_passed']),
#         'tests_failed': sum(1 for t in qc_summary.values() if t['any_run'] and not t['all_passed']),
#         'tests_pending': sum(1 for t in qc_summary.values() if not t['any_run']),
#         'total_runs_today': todays_results.count(),
#     }
    
#     # Recent failures (last 7 days)
#     recent_failures = QCResult.objects.filter(
#         vendor=vendor,
#         run_date__gte=today - timedelta(days=7),
#         status='FAIL'
#     ).select_related('qc_lot__test')[:10]
    
#     context = {
#         'qc_summary': qc_summary,
#         'stats': stats,
#         'recent_failures': recent_failures,
#         'today': today,
#     }
    
#     return render(request, 'laboratory/qc/dashboard.html', context)


# # ==========================================
# # QC ENTRY - Enter Daily QC Results
# # ==========================================

# # @login_required
# # def qc_entry(request):
# #     """
# #     Form to enter daily QC results.
# #     """
# #     vendor = request.user.vendor
# #     today = timezone.now().date()
    
# #     # Get active QC lots
# #     active_lots = QCLot.objects.filter(
# #         vendor=vendor,
# #         is_active=True,
# #         expiry_date__gte=today
# #     ).select_related('test').order_by('test__name', 'level')
    
# #     # Get instruments
# #     instruments = Equipment.objects.filter(
# #         vendor=vendor,
# #         status='active'
# #     )
    
# #     if request.method == 'POST':
# #         qc_lot_id = request.POST.get('qc_lot')
# #         result_value = request.POST.get('result_value')
# #         instrument_id = request.POST.get('instrument')
# #         run_number = request.POST.get('run_number', 1)
# #         comments = request.POST.get('comments', '')
        
# #         try:
# #             qc_lot = QCLot.objects.get(id=qc_lot_id, vendor=vendor)
# #             instrument = Equipment.objects.get(id=instrument_id, vendor=vendor) if instrument_id else None
            
# #             # Create QC result
# #             qc_result = QCResult.objects.create(
# #                 vendor=vendor,
# #                 qc_lot=qc_lot,
# #                 result_value=result_value,
# #                 run_date=today,
# #                 run_number=run_number,
# #                 instrument=instrument,
# #                 comments=comments,
# #                 entered_by=request.user
# #             )
            
# #             # Show status message
# #             if qc_result.status == 'PASS':
# #                 messages.success(
# #                     request,
# #                     f"✅ QC PASSED: {qc_lot.test.code} {qc_lot.get_level_display()} = {result_value} {qc_lot.units}"
# #                 )
# #             elif qc_result.status == 'WARNING':
# #                 messages.warning(
# #                     request,
# #                     f"⚠️ QC WARNING: {qc_lot.test.code} {qc_lot.get_level_display()} = {result_value} {qc_lot.units}"
# #                 )
# #             else:
# #                 messages.error(
# #                     request,
# #                     f"❌ QC FAILED: {qc_lot.test.code} {qc_lot.get_level_display()} = {result_value} {qc_lot.units}"
# #                 )
            
# #             return redirect('labs:qc_entry')
            
# #         except Exception as e:
# #             messages.error(request, f"Error saving QC result: {str(e)}")
    
# #     # Get today's results for display
# #     todays_results = QCResult.objects.filter(
# #         vendor=vendor,
# #         run_date=today
# #     ).select_related('qc_lot__test', 'instrument').order_by('-created_at')[:10]
    
# #     context = {
# #         'active_lots': active_lots,
# #         'instruments': instruments,
# #         'todays_results': todays_results,
# #         'today': today,
# #     }
    
# #     return render(request, 'laboratory/qc/entry.html', context)


# # ==========================================
# # LEVEY-JENNINGS CHART - Data Endpoint
# # ==========================================

# @login_required
# def levey_jennings_data(request, qc_lot_id):
#     """
#     API endpoint to get data for Levey-Jennings chart.
#     Returns JSON data for Chart.js.
#     """
#     vendor = request.user.vendor
#     qc_lot = get_object_or_404(QCLot, id=qc_lot_id, vendor=vendor)
    
#     # Get date range (default: last 30 days)
#     days = int(request.GET.get('days', 30))
#     start_date = timezone.now().date() - timedelta(days=days)
    
#     # Get QC results
#     results = QCResult.objects.filter(
#         qc_lot=qc_lot,
#         run_date__gte=start_date
#     ).order_by('run_date', 'run_time')
    
#     # Build chart data
#     labels = []
#     data_points = []
#     colors = []
    
#     for result in results:
#         labels.append(result.run_date.strftime('%m/%d'))
#         data_points.append(float(result.result_value))
        
#         # Color based on status
#         if result.status == 'PASS':
#             colors.append('rgba(75, 192, 192, 1)')  # Green
#         elif result.status == 'WARNING':
#             colors.append('rgba(255, 206, 86, 1)')  # Yellow
#         else:
#             colors.append('rgba(255, 99, 132, 1)')  # Red
    
#     # Control limits
#     chart_data = {
#         'labels': labels,
#         'datasets': [
#             {
#                 'label': 'QC Results',
#                 'data': data_points,
#                 'borderColor': 'rgba(54, 162, 235, 1)',
#                 'backgroundColor': colors,
#                 'pointBackgroundColor': colors,
#                 'pointBorderColor': colors,
#                 'pointRadius': 5,
#                 'fill': False,
#             }
#         ],
#         'control_limits': {
#             'mean': float(qc_lot.mean),
#             'sd_2_high': float(qc_lot.limit_2sd_high),
#             'sd_2_low': float(qc_lot.limit_2sd_low),
#             'sd_3_high': float(qc_lot.limit_3sd_high),
#             'sd_3_low': float(qc_lot.limit_3sd_low),
#         },
#         'lot_info': {
#             'test': qc_lot.test.name,
#             'level': qc_lot.get_level_display(),
#             'lot_number': qc_lot.lot_number,
#             'target': float(qc_lot.target_value),
#             'units': qc_lot.units,
#         }
#     }
    
#     return JsonResponse(chart_data)


# # ==========================================
# # LEVEY-JENNINGS CHART - View
# # ==========================================

# @login_required
# def levey_jennings_chart(request, qc_lot_id=None):
#     """
#     Display Levey-Jennings chart for a QC lot.
#     """
#     vendor = request.user.vendor
    
#     # Get all active QC lots for selection
#     active_lots = QCLot.objects.filter(
#         vendor=vendor,
#         is_active=True
#     ).select_related('test').order_by('test__name', 'level')
    
#     qc_lot = None
#     if qc_lot_id:
#         qc_lot = get_object_or_404(QCLot, id=qc_lot_id, vendor=vendor)
#     elif active_lots.exists():
#         qc_lot = active_lots.first()
    
#     context = {
#         'qc_lot': qc_lot,
#         'active_lots': active_lots,
#     }
    
#     return render(request, 'laboratory/qc/levey_jennings.html', context)


# # ==========================================
# # QC LOT MANAGEMENT
# # ==========================================

# @login_required
# def qc_lot_list(request):
#     """List all QC lots."""
#     vendor = request.user.vendor
    
#     lots = QCLot.objects.filter(
#         vendor=vendor
#     ).select_related('test').order_by('-is_active', '-received_date')
    
#     # Filter
#     test_filter = request.GET.get('test')
#     if test_filter:
#         lots = lots.filter(test_id=test_filter)
    
#     active_filter = request.GET.get('active')
#     if active_filter == 'true':
#         lots = lots.filter(is_active=True)
    
#     tests = VendorTest.objects.filter(vendor=vendor)
    
#     context = {
#         'lots': lots,
#         'tests': tests,
#         'current_test': test_filter,
#     }
    
#     return render(request, 'laboratory/qc/lot_list.html', context)


# from .forms import QCLotForm
# @login_required
# def qclot_create(request):
#     """Create new QC lot."""
#     vendor = request.user.vendor
    
#     if request.method == 'POST':
#         form = QCLotForm(request.POST, vendor=vendor)
#         if form.is_valid():
#             qc_lot = form.save(commit=False)
#             qc_lot.vendor = vendor
#             qc_lot.save()
#             messages.success(request, f"QC Lot {qc_lot.lot_number} created successfully.")
#             return redirect('labs:qclot_list')
#     else:
#         from .forms import QCLotForm
#         form = QCLotForm(vendor=vendor)
    
#     return render(request, 'laboratory/qc/qclot_form.html', {'form': form})


# # ==========================================
# # QC REPORTS
# # ==========================================

# @login_required
# def qc_monthly_report(request):
#     """Monthly QC summary report."""
#     vendor = request.user.vendor
    
#     # Get month and year from request or default to current
#     year = int(request.GET.get('year', timezone.now().year))
#     month = int(request.GET.get('month', timezone.now().month))
    
#     # Calculate date range
#     start_date = datetime(year, month, 1).date()
#     if month == 12:
#         end_date = datetime(year + 1, 1, 1).date() - timedelta(days=1)
#     else:
#         end_date = datetime(year, month + 1, 1).date() - timedelta(days=1)
    
#     # Get all QC results for the month
#     results = QCResult.objects.filter(
#         vendor=vendor,
#         run_date__gte=start_date,
#         run_date__lte=end_date
#     ).select_related('qc_lot__test')
    
#     # Summary statistics
#     total_runs = results.count()
#     passed = results.filter(status='PASS').count()
#     failed = results.filter(status='FAIL').count()
#     warnings = results.filter(status='WARNING').count()
    
#     pass_rate = (passed / total_runs * 100) if total_runs > 0 else 0
    
#     # Group by test
#     tests_summary = {}
#     for result in results:
#         test_code = result.qc_lot.test.code
#         if test_code not in tests_summary:
#             tests_summary[test_code] = {
#                 'test': result.qc_lot.test,
#                 'total': 0,
#                 'passed': 0,
#                 'failed': 0,
#                 'warnings': 0,
#             }
#         tests_summary[test_code]['total'] += 1
#         if result.status == 'PASS':
#             tests_summary[test_code]['passed'] += 1
#         elif result.status == 'FAIL':
#             tests_summary[test_code]['failed'] += 1
#         else:
#             tests_summary[test_code]['warnings'] += 1
    
#     context = {
#         'year': year,
#         'month': month,
#         'month_name': datetime(year, month, 1).strftime('%B %Y'),
#         'start_date': start_date,
#         'end_date': end_date,
#         'total_runs': total_runs,
#         'passed': passed,
#         'failed': failed,
#         'warnings': warnings,
#         'pass_rate': round(pass_rate, 1),
#         'tests_summary': tests_summary,
#     }
    
#     return render(request, 'laboratory/qc/monthly_report.html', context)