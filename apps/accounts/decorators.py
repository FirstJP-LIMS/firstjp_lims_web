from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages


def vendor_admin_required(view_func):
    """Decorator to ensure only vendor admins can access user management"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, 'Please log in to access this page.')
            return redirect('account:login')
        
        if not hasattr(request.user, 'vendor') or not request.user.vendor:
            messages.error(request, 'You must be associated with a laboratory.')
            return redirect('dashboard')
        
        if not request.user.is_vendor_admin:
            messages.error(request, 'Access denied. Only laboratory administrators can manage users.')
            return redirect('dashboard')
        
        return view_func(request, *args, **kwargs)
    
    return wrapper

