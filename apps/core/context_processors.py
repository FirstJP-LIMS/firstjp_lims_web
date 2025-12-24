from django.conf import settings

def platform_urls(request):
    return {
        "LEARN_BASE_URL": settings.LEARN_BASE_URL,
    }
