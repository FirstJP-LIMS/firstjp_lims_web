from django.apps import AppConfig


class DocControlConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.doc_control"
    verbose_name = 'Document Control System'
    
    def ready(self):
        """Import signals when app is ready"""
        # from . import signals
        import apps.doc_control.signals

