# In a templatetags/review_filters.py
from django import template
from django.utils import timezone

register = template.Library()

@register.filter
def filter_by_status(queryset, status):
    return queryset.filter(status=status)

@register.filter
def filter_by_overdue(queryset, value):
    if value:
        return queryset.filter(
            status='pending',
            due_date__lt=timezone.now().date()
        )
    return queryset.none()
