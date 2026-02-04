from django.contrib import admin
from apps.accounts.models import User, VendorProfile


"""
ADMIN
medvuno@gmail.com
medvuno

Vendor1 -- 
iarowosola@yahoo.com
password#12345

iarowosola25@gmail.com
password#1234567

"""


# Register your models here.
admin.site.register(User)
admin.site.register(VendorProfile)

