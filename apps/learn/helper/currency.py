# apps/helper/currency.py

def attach_display_price(course, currency_code, currency_symbol):
    if course.is_free:
        course.display_price = "Free"
        course.currency_symbol = ""
    else:
        course.display_price = convert_price(course.base_price, currency_code)
        course.currency_symbol = currency_symbol

    return course
