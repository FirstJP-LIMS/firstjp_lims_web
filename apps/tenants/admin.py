from django.contrib import admin
from apps.tenants.models import Vendor, VendorDomain


# superadmin 
# iarowosola@yahoo.com
# firstjp 

# Register your models here.
# admin.site.register(Vendor)

@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    # readonly_fields = ("name",)
    list_display = ('name', 'contact_email')

    # def get_readonly_fields(self, request, obj=None):
    #     if obj and obj.vendor.is_active:
    #         return ("domain_name", "is_primary", "vendor")
    #     return super().get_readonly_fields(request, obj)

@admin.register(VendorDomain)
class VendorDomainAdmin(admin.ModelAdmin):
    readonly_fields = ("domain_name",)

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.vendor.is_active:
            return ("domain_name", "is_primary", "vendor")
        return super().get_readonly_fields(request, obj)

