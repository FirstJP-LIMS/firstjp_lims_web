from django import template

register = template.Library()

@register.filter
def replace(value, arg):
    """
    Replaces all occurrences of one string with another
    Usage: {{ string|replace:"old,new" }}
    """
    try:
        old, new = arg.split(',')
        return value.replace(old, new)
    except:
        return value

@register.filter
def divide(value, arg):
    """Divide the value by the argument"""
    try:
        return float(value) / float(arg)
    except (ValueError, ZeroDivisionError, TypeError):
        return 0