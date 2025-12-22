# apps/learn/services/currency.py

# A simple map for currency display based on Country Code (ISO 3166-1 alpha-2)
# apps/learn/services/currency.py

COUNTRY_CURRENCY_MAP = {
    'US': ('USD', '$'),
    'NG': ('NGN', '₦'),
    'GB': ('GBP', '£'),
    'EU': ('EUR', '€'),
}

EXCHANGE_RATES = {
    'USD': 1.0,
    'NGN': 1600.0,
    'GBP': 0.8,
    'EUR': 0.9,
}

DEFAULT_CURRENCY = ('USD', '$')


def get_user_currency(request):
    country_code = (
        request.META.get('HTTP_CF_IPCOUNTRY') or
        request.META.get('GEOIP_COUNTRY_CODE')
    )

    if not country_code:
        return DEFAULT_CURRENCY[0], DEFAULT_CURRENCY[1], None

    currency, symbol = COUNTRY_CURRENCY_MAP.get(
        country_code.upper(),
        DEFAULT_CURRENCY
    )

    return currency, symbol, country_code.upper()


def convert_price(base_price_usd, currency_code):
    if base_price_usd == 0:
        return 0

    rate = EXCHANGE_RATES.get(currency_code, 1.0)
    return round(float(base_price_usd) * rate, 2)


def attach_display_price(course, currency_code, currency_symbol):
    if course.is_free:
        course.display_price = "Free"
        course.currency_symbol = ""
    else:
        course.display_price = convert_price(course.base_price, currency_code)
        course.currency_symbol = currency_symbol

    return course
