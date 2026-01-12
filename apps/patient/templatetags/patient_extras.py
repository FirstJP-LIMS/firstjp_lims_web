from django import template

register = template.Library()

@register.filter
def get_pending_count(queryset):
    return sum(1 for order in queryset.object_list if order.status == 'pending')

@register.filter
def get_completed_count(queryset):
    return sum(1 for order in queryset.object_list if order.status == 'completed')

@register.filter
def get_approval_count(queryset):
    return sum(1 for order in queryset.object_list if order.requires_approval)

@register.filter
def status_class(status):
    classes = {
        'pending': 'bg-yellow-100 text-yellow-800',
        'collected': 'bg-blue-100 text-blue-800',
        'processing': 'bg-purple-100 text-purple-800',
        'completed': 'bg-green-100 text-green-800',
        'cancelled': 'bg-red-100 text-red-800',
    }
    return classes.get(status, 'bg-gray-100 text-gray-800')

    

# register = template.Library()

@register.filter
def subtract(value, arg):
    """Subtract the arg from the value."""
    try:
        return int(value) - int(arg)
    except (ValueError, TypeError):
        return value

# In your template, load it with: {% load custom_filters %}