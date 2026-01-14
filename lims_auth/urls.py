"""
URL configuration for lims_auth project.
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
    
    path("notification/", include("apps.notification.urls", namespace="notification")),

    path("appointment/", include("apps.appointment.urls", namespace="appointment")),

    path("document-control/", include("apps.doc_control.urls", namespace="documents")),
    
    path("inventory/", include("apps.inventory.urls", namespace="inventory")),
    
    path("customer/", include("apps.patient.urls", namespace="patient")),
    
    path("clinician/", include("apps.clinician.urls", namespace="clinician")),

    path("academy/", include("apps.learn.urls", namespace="learn")),
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
    