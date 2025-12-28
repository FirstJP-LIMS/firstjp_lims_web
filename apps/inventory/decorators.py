# inventory/decorators.py
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.contrib import messages
from functools import wraps


"""
Custom decorators for inventory permission checks
-------------------------------------------------
@vendor_admin_required - For admin-only functions
@vendor_staff_required - For staff and above
@can_modify_inventory - For managers and admins
@permission_required_with_message - Enhanced Django permission check

"""

def vendor_admin_required(view_func):
    """
    Decorator to restrict access to vendor admins only.
    
    Usage:
        @login_required
        @vendor_admin_required
        def my_view(request):
            ...
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        # Check if user is authenticated (should be handled by @login_required)
        if not request.user.is_authenticated:
            return redirect('login')
        
        # Check if user has a vendor
        if not hasattr(request.user, 'vendor'):
            messages.error(request, 'You must be associated with a vendor to access this page.')
            return redirect('dashboard')
        
        # Check if user is vendor admin
        # Adjust this check based on your User model structure
        if not request.user.is_vendor_admin:  # or request.user.role == 'ADMIN'
            messages.error(
                request, 
                'Access denied. Only vendor administrators can perform this action.'
            )
            return redirect('inventory:dashboard')
        
        return view_func(request, *args, **kwargs)
    
    return wrapper


def vendor_staff_required(view_func):
    """
    Decorator to restrict access to vendor staff and admins.
    Less restrictive than vendor_admin_required.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        
        if not hasattr(request.user, 'vendor'):
            messages.error(request, 'You must be associated with a vendor.')
            return redirect('dashboard')
        
        # Check if user is staff or admin
        if not (request.user.is_vendor_admin or request.user.is_lab_staff):
            messages.error(request, 'Access denied. Insufficient permissions.')
            return redirect('inventory:dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper


def permission_required_with_message(perm):
    """
    Enhanced permission_required decorator with custom messages.
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            
            if not request.user.has_perm(perm):
                messages.error(
                    request,
                    f'You do not have permission to perform this action. Required: {perm}'
                )
                return redirect('inventory:dashboard')
            
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def can_modify_inventory(view_func):
    """
    Decorator to check if user can modify inventory (create, edit, delete).
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        
        # Check multiple conditions
        if not hasattr(request.user, 'vendor'):
            messages.error(request, 'No vendor association found.')
            return redirect('dashboard')
        
        # Check if user has permission OR is admin
        if not (request.user.is_vendor_admin or 
                request.user.has_perm('inventory.change_inventoryitem')):
            messages.error(
                request,
                'You do not have permission to modify inventory items.'
            )
            return redirect('inventory:dashboard')
        
        return view_func(request, *args, **kwargs)
    
    return wrapper

