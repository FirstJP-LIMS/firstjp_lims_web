from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages


def lab_technician_required(view_func):
    """
    Decorator for views that require lab technician access or higher.
    Lab technicians can enter results but cannot verify their own.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('account:login')
        
        if not hasattr(request.user, 'vendor'):
            messages.error(request, 'You must be associated with a laboratory vendor.')
            return redirect('labs:dashboard')
        
        # Check if user is lab technician, supervisor, or admin
        if not (request.user.is_lab_technician or 
                request.user.is_lab_supervisor or 
                request.user.is_vendor_admin):
            messages.error(
                request, 
                'Access denied. Only laboratory technicians can perform this action.'
            )
            return redirect('labs:result_list')
        return view_func(request, *args, **kwargs)
    return wrapper


def lab_supervisor_required(view_func):
    """
    Decorator for views that require lab supervisor access or higher.
    Lab supervisors can verify results entered by technicians.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('account:login')
        
        if not hasattr(request.user, 'vendor'):
            messages.error(request, 'You must be associated with a laboratory vendor.')
            return redirect('labs:dashboard')
        
        # Check if user is lab supervisor or admin
        if not (request.user.is_lab_supervisor or request.user.is_vendor_admin):
            messages.error(
                request, 
                'Access denied. Only laboratory supervisors can verify results.'
            )
            return redirect('labs:result_list')
        
        return view_func(request, *args, **kwargs)
    
    return wrapper


def lab_pathologist_required(view_func):
    """
    Decorator for views that require pathologist access or higher.
    Pathologists can release verified results to patients/doctors.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        
        if not hasattr(request.user, 'vendor'):
            messages.error(request, 'You must be associated with a laboratory vendor.')
            return redirect('dashboard')
        
        # Check if user is pathologist or admin
        if not (request.user.is_pathologist or request.user.is_vendor_admin):
            messages.error(
                request, 
                'Access denied. Only pathologists can release results.'
            )
            return redirect('labs:result_list')
        
        return view_func(request, *args, **kwargs)
    
    return wrapper


def can_amend_results(view_func):
    """
    Decorator for views that require permission to amend released results.
    Typically only lab directors/admins.
    
    Usage:
        @login_required
        @can_amend_results
        def amend_result(request):
            ...
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('account:login')
        
        if not hasattr(request.user, 'vendor'):
            messages.error(request, 'You must be associated with a laboratory vendor.')
            return redirect('dashboard')
        
        # Check if user has amendment permission (typically admin/director only)
        if not (request.user.is_vendor_admin or 
                request.user.has_perm('laboratory.can_amend_results')):
            messages.error(
                request, 
                'Access denied. Only authorized personnel can amend released results.'
            )
            return redirect('labs:result_list')
        
        return view_func(request, *args, **kwargs)
    
    return wrapper


def lab_staff_required(view_func):
    """
    Decorator for general lab staff access (any lab role).
    Less restrictive - allows any laboratory personnel.
    
    Usage:
        @login_required
        @lab_staff_required
        def view_results(request):
            ...
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('account:login')
        
        if not hasattr(request.user, 'vendor'):
            messages.error(request, 'You must be associated with a laboratory vendor.')
            return redirect('dashboard')
        
        # Check if user has any lab role
        if not (request.user.is_lab_technician or 
                request.user.is_lab_supervisor or 
                request.user.is_pathologist or
                request.user.is_vendor_admin):
            messages.error(
                request, 
                'Access denied. Only laboratory staff can access this page.'
            )
            return redirect('dashboard')
        
        return view_func(request, *args, **kwargs)
    
    return wrapper