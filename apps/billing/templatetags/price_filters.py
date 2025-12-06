from django import template

register = template.Library()

@register.filter
def calculate_discount(price, discount_percentage):
    """Calculate price after discount"""
    try:
        price = float(price)
        discount_percentage = float(discount_percentage or 0)
        if discount_percentage > 0:
            return price - (price * discount_percentage / 100)
        return price
    except (ValueError, TypeError):
        return price

@register.filter
def apply_tax(price, tax_percentage):
    """Calculate price after tax"""
    try:
        price = float(price)
        tax_percentage = float(tax_percentage or 0)
        if tax_percentage > 0:
            return price + (price * tax_percentage / 100)
        return price
    except (ValueError, TypeError):
        return price