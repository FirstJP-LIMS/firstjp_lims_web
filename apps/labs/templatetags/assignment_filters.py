from django import template

register = template.Library()

STATUS_COLORS = {
    'P': 'secondary',   # Pending
    'Q': 'info',        # Queued
    'I': 'warning',     # In Progress
    'A': 'primary',     # Analysis Done
    'V': 'success',     # Verified
    'R': 'danger',      # Rejected
}

@register.filter
def status_color(value):
    """Return bootstrap color class based on assignment status."""
    return STATUS_COLORS.get(value, 'secondary')










# # laboratory/templatetags/assignment_filters.py
# from django import template

# register = template.Library()

# @register.filter
# def status_color(status):
#     """Map assignment status to Bootstrap color classes"""
#     status_colors = {
#         'P': 'secondary',    # Pending - gray
#         'R': 'danger',       # Rejected - red
#         'Q': 'info',         # Queued - blue
#         'I': 'warning',      # In Progress - yellow
#         'A': 'primary',      # Analysis Complete - primary blue
#         'V': 'success',      # Result Verified - green
#     }
#     return status_colors.get(status, 'secondary')

# @register.filter
# def log_type_color(log_type):
#     """Map log type to Bootstrap color classes"""
#     log_colors = {
#         'send': 'primary',
#         'receive': 'success', 
#         'error': 'danger',
#     }
#     return log_colors.get(log_type, 'secondary')

# @register.filter
# def format_payload(payload):
#     """Format JSON payload for display"""
#     if isinstance(payload, dict):
#         return "\n".join([f"{key}: {value}" for key, value in payload.items()])
#     return str(payload)



