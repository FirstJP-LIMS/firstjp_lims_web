from django import template

register = template.Library()

@register.filter
def find_assignment(assignments, test):
    """Find assignment for a specific test"""
    for assignment in assignments:
        if assignment.lab_test == test:
            return assignment
    return None