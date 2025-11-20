from django.contrib import admin
from apps.tenants.models import Vendor, VendorDomain


# superadmin 
# iarowosola@yahoo.com
# firstjp 

# Register your models here.
admin.site.register(Vendor)
admin.site.register(VendorDomain)   

