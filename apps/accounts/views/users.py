# Staff Management Views with Enhanced Security and Functionality
import logging
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods, require_POST
from django.contrib import messages
from django.db import transaction
from django.contrib.auth import get_user_model
from django.db.models import Q, Count
from django.core.paginator import Paginator
from apps.labs.models import AuditLog, TestResult
from apps.labs.decorators import require_capability

User = get_user_model()
logger = logging.getLogger(__name__)

@login_required
@require_capability('can_manage_staff')
def user_list(request):
    """Refactored User List with Admin Statistics"""
    vendor = request.user.vendor

    # exclude roles 
    external_roles = ['patient', 'clinician', 'learner', 'facilitator', 'platform_admin']

    # users = User.objects.filter(vendor=vendor).exclude(id=request.user.id).order_by('-date_joined')
    users = User.objects.filter(
        vendor=vendor
    ).exclude(
        Q(id=request.user.id) |         # Exclude self
        Q(role__in=external_roles)    # Exclude patients/clinicians
    ).select_related('vendor').order_by('-date_joined')
    
    # Search & Filtering
    search_query = request.GET.get('search', '')
    if search_query:
        users = users.filter(
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(email__icontains=search_query)
        )
    
    role_filter = request.GET.get('role', '')
    if role_filter:
        users = users.filter(role=role_filter)

    # 4. Statistics (Adjusted for Staff only)
    # We use a reusable queryset to keep stats consistent with the list
    staff_base = User.objects.filter(vendor=vendor).exclude(role__in=external_roles)

    # # Statistics (Optimized)
    stats = {
        'total': staff_base.count(),
        'active': staff_base.filter(is_active=True).count(),
        'by_role': staff_base.values('role').annotate(count=Count('id')).order_by('-count')
    }

    paginator = Paginator(users, 20)
    page_obj = paginator.get_page(request.GET.get('page', 1))
    
    staff_roles = [
        choice for choice in User.ROLE_CHOICES 
        if choice[0] not in external_roles
        ]

    context = {
        'page_obj': page_obj,
        'stats': stats,
        'search_query': search_query,
        'available_roles':staff_roles,
    }

    return render(request, 'laboratory/staffs/staff_list.html', context)


@login_required
@require_capability('can_manage_staff')
@require_http_methods(["GET", "POST"])
def user_create(request):
    """Secure Staff Creation with strict role exclusion"""
    
    # Define roles that should NEVER be created through the staff management portal
    excluded_roles = ['patient', 'clinician', 'platform_admin', 'learner', 'facilitator']
    
    # Prepare the allowed roles list for both POST validation and GET context
    staff_roles = [
        choice for choice in User.ROLE_CHOICES 
        if choice[0] not in excluded_roles
    ]
    staff_role_codes = [r[0] for r in staff_roles]

    if request.method == "POST":
        email = request.POST.get('email', '').strip().lower()
        role = request.POST.get('role')
        password = request.POST.get('password')
        
        # 1. Security Check: Prevent "Role Injection" via POST manipulation
        if role not in staff_role_codes:
            messages.error(request, "Unauthorized role selection detected.")
            return redirect('users:user_list')

        # 2. Duplicate Check within the Vendor
        if User.objects.filter(email=email, vendor=request.user.vendor).exists():
            messages.error(request, "A user with this email already exists in your lab.")
            return render(request, 'laboratory/staffs/staff_form.html', {'available_roles': staff_roles})

        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    email=email,
                    password=password,
                    first_name=request.POST.get('first_name'),
                    last_name=request.POST.get('last_name'),
                    vendor=request.user.vendor,
                    role=role,
                    is_active=request.POST.get('is_active') == 'on'
                )
                
                # 3. High-Integrity Audit Log
                AuditLog.objects.create(
                    vendor=request.user.vendor,
                    user=request.user,
                    action=f"STAFF CREATED: {user.email} (Role: {user.get_role_display_name()})",
                    ip_address=request.META.get('REMOTE_ADDR')
                )
                
                messages.success(request, f"Staff member {user.get_full_name()} created successfully.")
                return redirect('users:user_detail', user_id=user.id)
                
        except Exception as e:
            messages.error(request, f"System Error: {str(e)}")

    # GET request: Render form with only staff roles
    context = {
        'available_roles': staff_roles,
        'action': 'Create Staff Member'
    }
    return render(request, 'laboratory/staffs/staff_form.html', context)


@login_required
@require_capability('can_manage_staff')
@require_POST
def user_change_role(request, user_id):
    """Quick Action: Role Change with Hierarchical Guard"""
    staff_member = get_object_or_404(User, id=user_id, vendor=request.user.vendor)
    new_role = request.POST.get('role')
    
    if staff_member == request.user:
        messages.error(request, "You cannot change your own role.")
        return redirect('users:user_list')

    if new_role == 'platform_admin':
        messages.error(request, "Permission Denied: Cannot promote to Platform Admin.")
        return redirect('users:user_list')

    old_role_display = staff_member.get_role_display_name()
    staff_member.role = new_role
    staff_member.save()

    AuditLog.objects.create(
        vendor=request.user.vendor,
        user=request.user,
        action=f"ROLE CHANGE: {staff_member.email} from {old_role_display} to {staff_member.get_role_display_name()}",
        ip_address=request.META.get('REMOTE_ADDR')
    )
    
    messages.success(request, "Role updated successfully.")
    return redirect('users:user_list')


@login_required
@require_capability('can_manage_staff')
@require_POST
def user_toggle_status(request, user_id):
    """Toggle Active/Inactive Status"""
    staff_member = get_object_or_404(User, id=user_id, vendor=request.user.vendor)
    
    if staff_member == request.user:
        messages.error(request, "Cannot deactivate yourself.")
        return redirect('users:user_list')

    staff_member.is_active = not staff_member.is_active
    staff_member.save()
    
    status_str = "ACTIVATED" if staff_member.is_active else "DEACTIVATED"
    AuditLog.objects.create(
        vendor=request.user.vendor,
        user=request.user,
        action=f"STATUS CHANGE: {staff_member.email} set to {status_str}",
        ip_address=request.META.get('REMOTE_ADDR')
    )
    
    messages.success(request, f"User {status_str.lower()} successfully.")
    return redirect('users:user_detail', user_id=staff_member.id)


@login_required
@require_capability('can_manage_staff')
@require_POST
def user_suspend(request, user_id):
    """
    Suspends a user account and records the administrative reason.
    """
    staff_member = get_object_or_404(User, id=user_id, vendor=request.user.vendor)
    reason = request.POST.get('reason', '').strip()

    if staff_member == request.user:
        messages.error(request, "You cannot suspend your own account.")
        return redirect('users:user_detail', user_id=staff_member.id)

    if not reason:
        messages.error(request, "A reason for suspension is required for the audit trail.")
        return redirect('users:user_detail', user_id=staff_member.id)

    try:
        with transaction.atomic():
            staff_member.is_active = False
            staff_member.save(update_fields=['is_active'])
            
            # Detailed Audit Log for Suspension
            AuditLog.objects.create(
                vendor=request.user.vendor,
                user=request.user,
                action=f"SUSPENDED USER: {staff_member.email}. Reason: {reason}",
                ip_address=request.META.get('REMOTE_ADDR')
            )
            
        messages.warning(request, f"User {staff_member.get_full_name()} has been suspended.")
    except Exception as e:
        messages.error(request, f"Suspension failed: {str(e)}")
        
    return redirect('users:user_detail', user_id=staff_member.id)


@login_required
@require_capability('can_manage_staff')
@require_POST
def user_deactivate(request, user_id):
    """
    Deactivates a user account. 
    This is used for offboarding or temporary access removal.
    """
    staff_member = get_object_or_404(User, id=user_id, vendor=request.user.vendor)
    
    if staff_member == request.user:
        messages.error(request, "You cannot deactivate your own administrative account.")
        return redirect('users:user_detail', user_id=staff_member.id)

    staff_member.is_active = False
    staff_member.save(update_fields=['is_active'])

    AuditLog.objects.create(
        vendor=request.user.vendor,
        user=request.user,
        action=f"DEACTIVATED ACCOUNT: {staff_member.get_full_name()} ({staff_member.email})",
        ip_address=request.META.get('REMOTE_ADDR')
    )    
    messages.success(request, f"Access for {staff_member.get_full_name()} has been revoked.")
    return redirect('users:user_detail', user_id=staff_member.id)


@login_required
def user_detail(request, user_id):
    """
    Comprehensive view of a staff member's profile, permissions, and productivity.
    """
    vendor = request.user.vendor
    # Profile_user is the target, request.user is the admin viewing it
    profile_user = get_object_or_404(User, id=user_id, vendor=vendor)
    
    # 1. Fetch Audit Logs for this specific user's actions
    recent_activity = AuditLog.objects.filter(
        user=profile_user,
        vendor=vendor
    ).order_by('-timestamp')[:15] # Most recent 15 actions

    # 2. Performance Metrics (Productivity)
    # This helps a manager see if a technician is keeping up with their workload
    metrics = {
        'entered': TestResult.objects.filter(entered_by=profile_user).count(),
        'verified': TestResult.objects.filter(verified_by=profile_user).count(),
        'released': TestResult.objects.filter(released_by=profile_user).count(),
    }

    # 3. Permission Summary
    # Uses the get_permissions_summary() method from your User model
    permissions = profile_user.get_permissions_summary()

    context = {
        'profile_user': profile_user,
        'recent_activity': recent_activity,
        'metrics': metrics,
        'permissions': permissions,
    }
    
    return render(request, 'laboratory/staffs/staff_detail.html', context)



from django.utils import timezone
from datetime import datetime

@login_required
@require_capability('can_manage_staff')
def full_audit_log(request):
    """
    Forensic search for all laboratory actions.
    """
    vendor = request.user.vendor
    logs = AuditLog.objects.filter(vendor=vendor).select_related('user').order_by('-timestamp')

    # 1. Filter by Specific User
    user_id = request.GET.get('user_id')
    if user_id:
        logs = logs.filter(user_id=user_id)

    # 2. Filter by Action Type (Search in the string)
    action_query = request.GET.get('action_type')
    if action_query:
        logs = logs.filter(action__icontains=action_query)

    # 3. Date Range Filtering
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    if start_date and end_date:
        try:
            # Parse dates and make them timezone aware
            start = timezone.make_aware(datetime.strptime(start_date, '%Y-%m-%d'))
            end = timezone.make_aware(datetime.strptime(end_date, '%Y-%m-%d').replace(hour=23, minute=59))
            logs = logs.filter(timestamp__range=(start, end))
        except ValueError:
            messages.error(request, "Invalid date format. Use YYYY-MM-DD.")

    # Pagination
    paginator = Paginator(logs, 50) # Higher limit for logs
    page_obj = paginator.get_page(request.GET.get('page', 1))

    # For the filter dropdown
    staff_list = User.objects.filter(vendor=vendor).only('id', 'first_name', 'last_name', 'email')

    context = {
        'page_obj': page_obj,
        'staff_list': staff_list,
        'filters': request.GET
    }
    return render(request, 'laboratory/staffs/audit/audit_list.html', context)

