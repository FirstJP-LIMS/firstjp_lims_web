from django import template
from django.utils import timezone
from datetime import datetime
import re

register = template.Library()

@register.filter
def get_pending_count(queryset):
    """Get count of pending orders in queryset."""
    if not queryset:
        return 0
    return sum(1 for order in queryset.object_list if order.status == 'pending')

@register.filter
def get_completed_count(queryset):
    """Get count of completed orders in queryset."""
    if not queryset:
        return 0
    return sum(1 for order in queryset.object_list if order.status == 'completed')

@register.filter
def get_cancelled_count(queryset):
    """Get count of cancelled orders."""
    if not queryset:
        return 0
    return sum(1 for order in queryset.object_list if order.status == 'cancelled')

@register.filter
def get_today_count(queryset):
    """Get count of orders created today."""
    if not queryset:
        return 0
    today = timezone.now().date()
    return sum(1 for order in queryset.object_list if order.created_at.date() == today)

@register.filter
def status_class(status):
    """Return CSS class for status badge."""
    classes = {
        'pending': 'bg-yellow-100 text-yellow-800',
        'collected': 'bg-blue-100 text-blue-800',
        'processing': 'bg-purple-100 text-purple-800',
        'completed': 'bg-green-100 text-green-800',
        'cancelled': 'bg-red-100 text-red-800',
    }
    return classes.get(status, 'bg-gray-100 text-gray-800')

@register.filter
def priority_class(priority):
    """Return CSS class for priority badge."""
    classes = {
        'urgent': 'bg-red-100 text-red-800',
        'routine': 'bg-blue-100 text-blue-800',
    }
    return classes.get(priority, 'bg-gray-100 text-gray-800')


@register.filter
def split(value, delimiter):
    """Split a string by delimiter."""
    return value.split(delimiter)

