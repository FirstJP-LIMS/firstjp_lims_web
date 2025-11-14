# laboratory/templatetags/laboratory_tags.py
from django import template
from django.utils.safestring import mark_safe
import json

register = template.Library()

@register.filter
def status_color(status):
    """Return Bootstrap color class for assignment status"""
    colors = {
        'P': 'warning',
        'R': 'danger',
        'Q': 'info',
        'I': 'secondary',
        'A': 'primary',
        'V': 'success',
    }
    return colors.get(status, 'secondary')


@register.filter
def priority_color(priority):
    """Return Bootstrap color class for priority"""
    colors = {
        'stat': 'danger',
        'urgent': 'warning',
        'routine': 'info',
    }
    return colors.get(priority.lower(), 'info')


@register.filter
def flag_color(flag):
    """Return Bootstrap color class for result flag"""
    colors = {
        'N': 'success',
        'H': 'danger',
        'L': 'warning',
        'A': 'secondary',
        'C': 'danger',
    }
    return colors.get(flag, 'secondary')


@register.filter
def pprint(value):
    """Pretty print JSON for display"""
    try:
        if isinstance(value, str):
            value = json.loads(value)
        return json.dumps(value, indent=2)
    except:
        return str(value)


@register.simple_tag
def query_transform(request, **kwargs):
    """
    Add or update query parameters while preserving existing ones.
    Usage: {% query_transform request page=2 %}
    """
    updated = request.GET.copy()
    for key, value in kwargs.items():
        if value is not None:
            updated[key] = value
        elif key in updated:
            del updated[key]
    return updated.urlencode()


@register.filter
def duration_human(duration):
    """Convert timedelta to human-readable format"""
    if not duration:
        return "N/A"
    
    total_seconds = int(duration.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    parts = []
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if seconds > 0 or not parts:
        parts.append(f"{seconds}s")
    
    return " ".join(parts)


@register.filter
def percentage(value, total):
    """Calculate percentage"""
    try:
        if total == 0:
            return 0
        return round((value / total) * 100, 1)
    except:
        return 0


@register.inclusion_tag('laboratory/includes/status_badge.html')
def status_badge(status, size='sm'):
    """Render a status badge with icon"""
    return {
        'status': status,
        'size': size,
    }


@register.inclusion_tag('laboratory/includes/priority_badge.html')
def priority_badge(priority, size='sm'):
    """Render a priority badge"""
    return {
        'priority': priority,
        'size': size,
    }


@register.filter
def get_item(dictionary, key):
    """Get item from dictionary in template"""
    return dictionary.get(key)


@register.simple_tag
def assignment_turnaround_time(assignment):
    """Calculate turnaround time for assignment"""
    if not assignment.analyzed_at or not assignment.queued_at:
        return "Pending"
    
    delta = assignment.analyzed_at - assignment.queued_at
    return duration_human(delta)


@register.filter
def can_perform_action(assignment, action):
    """Check if user can perform specific action on assignment"""
    if action == 'send':
        return assignment.can_send_to_instrument()
    elif action == 'verify':
        return (
            hasattr(assignment, 'result') and 
            assignment.status == 'A' and 
            not assignment.result.verified_at
        )
    elif action == 'release':
        return (
            hasattr(assignment, 'result') and 
            assignment.result.verified_at and 
            not assignment.result.released
        )
    return False