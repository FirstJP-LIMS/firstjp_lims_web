from django.contrib import admin
from apps.accounts.models import User, VendorProfile


"""
first@gmail.com
first
"""

# Register your models here.
admin.site.register(User)
admin.site.register(VendorProfile)
