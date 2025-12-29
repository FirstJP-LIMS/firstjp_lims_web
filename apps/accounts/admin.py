from django.contrib import admin
from apps.accounts.models import User, VendorProfile


"""
ADMIN
medvuno@gmail.com
medvuno

Vendor1 -- http://olulori.localhost.test:8000
ADMIN
lastborn.ai@gmail.com
carboni#12345

kilas@gmail.com
password#1111
"""


# Register your models here.
admin.site.register(User)
admin.site.register(VendorProfile)

