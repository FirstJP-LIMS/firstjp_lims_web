from django.urls import path
from . import views as views_admin

urlpatterns = [
    path("admin/vendors/", views_admin.admin_vendor_list, name="admin_vendor_list"),
    path("admin/vendors/<uuid:vendor_id>/activate/", views_admin.activate_vendor, name="activate_vendor"),
]
