from django.apps import AppConfig


class AppointmentConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.appointment"
    # def ready(self):
    #     import apps.appointment.signals # This triggers the registration
    