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

# Logger Setup
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)




# **************************************************
# Phase 3:
# Post Examination Section
# ---- Post test, get result, and prepare result 
    # TestAssignment → represents a job sent to the instrument.
    # TestResult → holds result data.
    # VendorTest → defines reference range (min/max).
# ***************************************************
# ******************
# Test Assignment
# ******************

@login_required
def test_assignment_list(request):
    """
    List all test assignments with filtering, search, instrument assignment, and bulk actions.
    """
    vendor = request.user.vendor
    
    # Base queryset with optimized queries
    assignments = TestAssignment.objects.filter(
        vendor=vendor
    ).select_related(
        'lab_test',
        'request__patient',
        'sample',
        'instrument',
        'department',
        'assigned_to'
    ).prefetch_related(
        Prefetch('result', queryset=TestResult.objects.select_related('entered_by', 'verified_by'))
    )
    
    # Get filter parameters
    status_filter = request.GET.get('status', '')
    department_filter = request.GET.get('department', '')
    instrument_filter = request.GET.get('instrument', '')
    priority_filter = request.GET.get('priority', '')
    search_query = request.GET.get('search', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    
    # Apply filters
    if status_filter:
        assignments = assignments.filter(status=status_filter)
    
    if department_filter:
        assignments = assignments.filter(department_id=department_filter)
    
    if instrument_filter:
        if instrument_filter == 'unassigned':
            assignments = assignments.filter(instrument__isnull=True)
        else:
            assignments = assignments.filter(instrument_id=instrument_filter)
    
    if priority_filter:
        assignments = assignments.filter(request__priority=priority_filter)
    
    if search_query:
        assignments = assignments.filter(
            Q(request__request_id__icontains=search_query) |
            Q(request__patient__patient_id__icontains=search_query) |
            Q(request__patient__first_name__icontains=search_query) |
            Q(request__patient__last_name__icontains=search_query) |
            Q(lab_test__name__icontains=search_query) |
            Q(lab_test__code__icontains=search_query) |
            Q(sample__sample_id__icontains=search_query)
        )
    
    if date_from:
        assignments = assignments.filter(created_at__gte=date_from)
    
    if date_to:
        assignments = assignments.filter(created_at__lte=date_to)
    
    # Get ordering
    order_by = request.GET.get('order_by', '-created_at')
    assignments = assignments.order_by(order_by)
    
    # Get statistics for dashboard cards
    stats = {
        'total': assignments.count(),
        'pending': assignments.filter(status='P').count(),
        'queued': assignments.filter(status='Q').count(),
        'in_progress': assignments.filter(status='I').count(),
        'completed': assignments.filter(status='A').count(),
        'verified': assignments.filter(status='V').count(),
        'rejected': assignments.filter(status='R').count(),
        # NEW: Unassigned instruments stat
        'unassigned_instruments': assignments.filter(
            status='P',
            instrument__isnull=True
        ).count(),
    }
    
    # Pagination
    paginator = Paginator(assignments, 25)  # 25 items per page
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    # Get filter options for dropdowns
    departments = Department.objects.filter(vendor=vendor)
    instruments = Equipment.objects.filter(vendor=vendor, status='active')
    
    # NEW: Get available instruments for quick assignment (active only)
    available_instruments = Equipment.objects.filter(
        vendor=vendor,
        status='active'
    ).select_related('department').order_by('department__name', 'name')
    
    context = {
        'page_obj': page_obj,
        'assignments': page_obj.object_list,
        'stats': stats,
        'departments': departments,
        'instruments': instruments,
        'available_instruments': available_instruments,  # NEW
        
        # Current filters (to maintain state)
        'current_status': status_filter,
        'current_department': department_filter,
        'current_instrument': instrument_filter,
        'current_priority': priority_filter,
        'search_query': search_query,
        'date_from': date_from,
        'date_to': date_to,
        'order_by': order_by,
        
        # Available options
        'status_choices': TestAssignment.ASSIGNMENT_STATUS,
        'priority_choices': [
            ('routine', 'Routine'),
            ('urgent', 'Urgent'),
            ('stat', 'STAT'),
        ],
    }
    
    return render(request, 'laboratory/assignment/test_assignment_list.html', context)


@login_required
def test_assignment_detail(request, assignment_id):
    """View detailed information about a test assignment"""
    assignment = get_object_or_404(
        TestAssignment.objects.select_related(
            'lab_test',
            'request__patient',
            'sample',
            'instrument',
            'department',
            'assigned_to'
        ).prefetch_related('instrument_logs'),
        id=assignment_id,
        vendor=request.user.vendor
    )
    
    # Get result if exists
    result = getattr(assignment, 'result', None)
    
    # Get communication logs
    logs = assignment.instrument_logs.all()[:10]
    
    context = {
        'assignment': assignment,
        'result': result,
        'logs': logs,
        'can_send': assignment.can_send_to_instrument(),
        'can_verify': (
            result and 
            not result.verified_at and 
            result.entered_by != request.user
        ),
        'can_release': result and result.verified_at and not result.released,
    }
    
    return render(request, 'laboratory/assignment/test_assignment_detail.html', context)



@login_required
def assignment_quick_stats(request):
    """
    AJAX endpoint for real-time stats updates.
    """
    vendor = request.user.vendor
    
    stats = TestAssignment.objects.filter(vendor=vendor).aggregate(
        total=Count('id'),
        pending=Count('id', filter=Q(status='P')),
        queued=Count('id', filter=Q(status='Q')),
        in_progress=Count('id', filter=Q(status='I')),
        completed=Count('id', filter=Q(status='A')),
        verified=Count('id', filter=Q(status='V')),
    )
    
    return JsonResponse(stats)


