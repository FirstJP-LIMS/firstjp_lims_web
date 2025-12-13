from django.contrib import admin
from apps.accounts.models import User, VendorProfile


"""
first@gmail.com
first
# lastborn.ai1@gmail.com
passmark#1234

patient

patient
lastborn.ai2@gmail.com
password#12345

clinician
ned@gmail.com
password#1234
"""


# Register your models here.
admin.site.register(User)
admin.site.register(VendorProfile)
