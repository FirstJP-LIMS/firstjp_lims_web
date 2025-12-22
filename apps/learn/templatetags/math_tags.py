# learn/templatetags/math_tags.py

from django import template

# Get a Django template Library instance
register = template.Library()

@register.filter
def div(value, arg):
    """
    Divides the value by the argument.
    e.g., {{ lesson.duration_seconds|div:60 }}
    """
    try:
        # Ensure values are converted to numbers for division
        return int(value) / int(arg)
    except (ValueError, ZeroDivisionError, TypeError):
        # Return 0 or handle error gracefully if input is invalid
        return 0
    