from django import template

register = template.Library()

@register.filter
def duration_format(seconds):
    """Convert seconds to HH:MM:SS format"""
    if not seconds:
        return "0 min"
    
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    
    if hours > 0:
        return f"{hours}h {minutes}m"
    elif minutes > 0:
        return f"{minutes}m {secs}s"
    else:
        return f"{secs}s"

@register.filter
def status_count(queryset, status):
    """Count items with specific status"""
    return queryset.filter(status=status).count()
