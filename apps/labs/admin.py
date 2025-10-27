from django.contrib import admin
from . import models

# Register your models here.
admin.site.register(models.Department)
admin.site.register(models.GlobalTest)
admin.site.register(models.VendorTest)
admin.site.register(models.Patient)
admin.site.register(models.Sample)
admin.site.register(models.TestRequest)
admin.site.register(models.TestAssignment)
admin.site.register(models.TestResult)
admin.site.register(models.Equipment)
admin.site.register(models.AuditLog)