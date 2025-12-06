"""
URL configuration for lims_auth project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),
    path('', include('apps.core.urls')),
    path("account/", include("apps.accounts.urls", namespace="account")),
    path("tenants/", include("apps.tenants.urls")),
    path("laboratory/", include("apps.labs.urls", namespace="labs")),
    path("billing/", include("apps.billing.urls", namespace="billing")),
    path("lms/", include("apps.lms.urls", namespace="lms")),
]

# Static & media files (always included)
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Debug Toolbar & Browser Reload (development only)
if settings.DEBUG:
    try:
        import debug_toolbar
        urlpatterns += [
            path("__debug__/", include(debug_toolbar.urls)),
        ]
    except ImportError:
        pass
    
    try:
        urlpatterns += [
            path("__reload__/", include("django_browser_reload.urls")),
        ]
    except:
        pass