from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages


def require_capability(capability):
    """
    Global decorator:
    Enforces user capability as defined on the User model.
    """

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):

            if not request.user.is_authenticated:
                return redirect("account:login")

            if not getattr(request.user, "vendor", None):
                messages.error(request, "You are not associated with a laboratory.")
                return redirect("account:login")  # to route to Medvuno landing page

            if not hasattr(request.user, capability):
                messages.error(request, "System misconfiguration: capability not found.")
                return redirect("labs:vendor_dashboard")

            if not getattr(request.user, capability):
                messages.error(
                    request,
                    "Access denied. You are not authorized to perform this action."
                )
                return redirect("labs:result_list")

            return view_func(request, *args, **kwargs)

        return wrapper
    return decorator


