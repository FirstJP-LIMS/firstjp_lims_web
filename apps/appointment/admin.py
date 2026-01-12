from django.contrib import admin
from . import models

# Register your models here.
admin.site.register(models.Appointment)
admin.site.register(models.AppointmentSlot)
admin.site.register(models.AppointmentSlotTemplate)

