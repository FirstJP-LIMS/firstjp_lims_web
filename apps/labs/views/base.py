import logging
from datetime import timedelta
from functools import wraps

# Django Core
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import (
    Avg, Count, DurationField, ExpressionWrapper, F, Q
)
from django.http import HttpResponseForbidden
from django.shortcuts import render
from django.urls import reverse, reverse_lazy
from django.utils import timezone

# App-Specific Imports

from ..models import (
    Equipment,
    Sample,
    TestAssignment,
)

from ..utils import check_tenant_access


# Logger Setup
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


# --- Decorator Definition ---
def tenant_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        tenant, is_platform_admin = check_tenant_access(request)
        if not tenant and not is_platform_admin:
            return HttpResponseForbidden("Access Denied: Tenant or User Mismatch.")
        # Attach resolved values to request for easy use in the view
        request.tenant = tenant
        request.is_platform_admin = is_platform_admin
        return view_func(request, *args, **kwargs)
    return _wrapped_view


# --- CRM Views ---
@login_required
@tenant_required
def dashboard(request):
    tenant = request.tenant
    is_platform_admin = request.is_platform_admin
    if is_platform_admin and not tenant:
        # Assuming you have a login URL or process for platform admins without a tenant
        # return redirect("platform_admin_select_tenant") 
        pass 

    # Fetch lab Departments for the header (as in your original code)
    try:
        lab_departments = tenant.departments.all().order_by('name')
    except AttributeError:
        lab_departments = []

    lab_name = getattr(tenant, 'business_name', tenant.name)
    now = timezone.now()

    # --- 1. Calculate Time Ranges for Filtering ---
    date_filter = request.GET.get("filter", "7days")
    
    if date_filter == "today":
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        previous_start_date = start_date - timedelta(days=1)
    elif date_filter == "30days":
        start_date = now - timedelta(days=30)
        previous_start_date = now - timedelta(days=60)
    else:  # Default to 7days
        start_date = now - timedelta(days=7)
        previous_start_date = now - timedelta(days=14)

    # --- 2. Fetch Dashboard Statistics ---
    # Base query for Assignments
    assignment_base_qs = TestAssignment.objects.filter(vendor=tenant)
    sample_base_qs = Sample.objects.filter(vendor=tenant)

    # 2.1. Pending Samples/Assignments (P, Q, I status within the current filter period)
    pending_assignments_count = assignment_base_qs.filter(
        status__in=['P', 'Q', 'I'],
        created_at__gte=start_date
    ).count()

    # 2.2. Unverified Results (Assignments that are Analyzed (A) but not Verified/Released (V/R))
    # Filtered by the current time period to keep the count relevant to the date filter
    unread_results_count = assignment_base_qs.filter(
        status__in=['A'], 
        updated_at__gte=start_date 
    ).count()

    # 2.3. Total Samples processed (for trends)
    current_samples_count = sample_base_qs.filter(collected_at__gte=start_date).count()
    previous_samples_count = sample_base_qs.filter(
        collected_at__gte=previous_start_date, 
        collected_at__lt=start_date
    ).count()

    # Trend calculation
    samples_trend_percent = 0
    if previous_samples_count > 0:
        samples_trend_percent = round(((current_samples_count - previous_samples_count) / previous_samples_count) * 100, 1)
    elif current_samples_count > 0:
        samples_trend_percent = 100.0
        
    # Determine trend direction
    trend_direction = "up" if samples_trend_percent >= 0 else "down"

    # 2.4. Monthly Samples (always 30 days)
    monthly_samples_count = sample_base_qs.filter(
        collected_at__gte=now - timedelta(days=30)
    ).count()
    
    # 2.5. Average TAT (from creation to verification/release)
    avg_tat_display = "N/A"
    tat_qs = assignment_base_qs.filter(status__in=['V', 'R']).annotate(
        tat_duration=ExpressionWrapper(
            F('verified_at') - F('created_at'),
            output_field=DurationField()
        )
    )
    avg_tat_result = tat_qs.aggregate(Avg('tat_duration'))['tat_duration__avg']

    if avg_tat_result:
        total_seconds = avg_tat_result.total_seconds()
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        # Format: e.g., 4h 30m
        avg_tat_display = f"{hours}h {minutes}m"
        
    # --- 3. Equipment Status (NEW SECTION) ---
    equipment_qs = Equipment.objects.filter(vendor=tenant).select_related('department')
    
    equipment_with_stats = equipment_qs.annotate(
        pending_tests=Count(
            'assignments',
            filter=Q(assignments__status__in=['P', 'Q', 'I'])
        ),
        total_tests_today=Count(
            'assignments',
            filter=Q(assignments__created_at__gte=now.replace(hour=0, minute=0, second=0, microsecond=0))
        )
    ).order_by('-status', 'name')
    
    dashboard_equipment = equipment_with_stats[:5]
    
    equipment_stats = {
        'total': equipment_qs.count(),
        'active': equipment_qs.filter(status='active').count(),
        'maintenance': equipment_qs.filter(status='maintenance').count(),
        'inactive': equipment_qs.filter(status='inactive').count(),
        'configured': equipment_qs.exclude(api_endpoint='').count(),
        'unconfigured': equipment_qs.filter(api_endpoint='').count(),
    }

    # --- 4. Pagination for Recent Samples ---
    samples_qs = Sample.objects.filter(vendor=tenant, collected_at__gte=start_date).order_by('-collected_at')
    paginator = Paginator(samples_qs, 10)
    page_number = request.GET.get("page")
    samples_page = paginator.get_page(page_number)

    context = {
        "vendor": tenant,
        "lab_name": lab_name,
        "vendor_domain": tenant.domains.first().domain_name if tenant.domains.exists() else 'N/A',
        "lab_departments": lab_departments,
        "samples": samples_page,
        "current_filter": date_filter,
        
        # New Statistics Context
        "pending_assignments_count": pending_assignments_count,
        "samples_in_period_count": current_samples_count,
        "samples_trend_percent": abs(samples_trend_percent),
        "samples_trend_direction": trend_direction,
        "avg_tat_display": avg_tat_display,
        "unread_results_count": unread_results_count,
        "monthly_samples_count": monthly_samples_count,

        # NEW: Equipment Context
        "dashboard_equipment": dashboard_equipment,
        "equipment_stats": equipment_stats,
    }
    return render(request, "laboratory/dashboard.html", context)



# lab view
@login_required
@tenant_required
def lab_assistants(request):
    tenant = request.tenant
    assistants = request.user._meta.model.objects.filter(vendor=tenant, role='lab_staff')
    return render(request, "labs/assistants.html", {"assistants": assistants})


# improvements: Vendor's Logo
@login_required
@tenant_required
def profile(request):
    return render(request,"labs/profile.html",
        {"vendor": request.tenant, "user": request.user}
    )

