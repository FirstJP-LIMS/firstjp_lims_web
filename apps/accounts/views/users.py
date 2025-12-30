import logging
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods, require_POST
from django.contrib import messages
from django.db import transaction
from django.contrib.auth import get_user_model
from django.db.models import Q, Count
from django.core.paginator import Paginator
from apps.labs.models import AuditLog, TestResult  # Centralized imports
from ..decorators import vendor_admin_required # Use your new decorator

User = get_user_model()
logger = logging.getLogger(__name__)

@login_required
@vendor_admin_required
def user_list(request):
    """Refactored User List with Admin Statistics"""
    vendor = request.user.vendor
    users = User.objects.filter(vendor=vendor).exclude(id=request.user.id).order_by('-date_joined')
    
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

    # Statistics (Optimized)
    stats = {
        'total': User.objects.filter(vendor=vendor).count(),
        'active': User.objects.filter(vendor=vendor, is_active=True).count(),
        'by_role': User.objects.filter(vendor=vendor).values('role').annotate(count=Count('id'))
    }
    
    paginator = Paginator(users, 20)
    page_obj = paginator.get_page(request.GET.get('page', 1))
    
    context = {
        'page_obj': page_obj,
        'stats': stats,
        'search_query': search_query,
        'available_roles': [c for c in User.ROLE_CHOICES if c[0] != 'platform_admin'],
    }
    return render(request, 'users/user_list.html', context)

@login_required
@vendor_admin_required
@require_http_methods(["GET", "POST"])
def user_create(request):
    """Secure User Creation with Audit Log"""
    if request.method == "POST":
        email = request.POST.get('email', '').strip().lower()
        role = request.POST.get('role')
        password = request.POST.get('password')
        
        # Validation Logic
        if User.objects.filter(email=email, vendor=request.user.vendor).exists():
            messages.error(request, "User already exists in your laboratory.")
            return redirect('users:user_create')

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
                
                AuditLog.objects.create(
                    vendor=request.user.vendor,
                    user=request.user,
                    action=f"CREATED USER: {user.email} as {user.get_role_display_name()}",
                    ip_address=request.META.get('REMOTE_ADDR')
                )
                messages.success(request, f"User {user.email} created.")
                return redirect('users:user_detail', user_id=user.id)
        except Exception as e:
            messages.error(request, f"Error: {str(e)}")

    return render(request, 'users/user_form.html', {'available_roles': [c for c in User.ROLE_CHOICES if c[0] != 'platform_admin']})


@login_required
@vendor_admin_required
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
@vendor_admin_required
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
@vendor_admin_required
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
@vendor_admin_required
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
@vendor_admin_required
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
    
    return render(request, 'users/user_detail.html', context)
