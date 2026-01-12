from django.db import migrations


def seed_system_notification_templates(apps, schema_editor):
    NotificationTemplate = apps.get_model('notification', 'NotificationTemplate')

    templates = [
        # Appointment booked (IN-APP)
        {
            "vendor": None,
            "notification_type": "appointment_booked",
            "channel": "in_app",
            "subject": "Appointment Booked",
            "body": (
                "Your appointment for {{ test_name }} "
                "has been scheduled on {{ appointment_date }}."
            ),
            "is_active": True,
        },

        # Appointment booked (EMAIL)
        {
            "vendor": None,
            "notification_type": "appointment_booked",
            "channel": "email",
            "subject": "Appointment Confirmation",
            "body": (
                "Dear {{ patient_name }},\n\n"
                "Your appointment for {{ test_name }} is confirmed "
                "for {{ appointment_date }}.\n\n"
                "Thank you."
            ),
            "is_active": True,
        },

        # Appointment cancelled (IN-APP)
        {
            "vendor": None,
            "notification_type": "appointment_cancelled",
            "channel": "in_app",
            "subject": "Appointment Cancelled",
            "body": (
                "Your appointment for {{ test_name }} "
                "scheduled on {{ appointment_date }} has been cancelled."
            ),
            "is_active": True,
        },
    ]

    for data in templates:
        NotificationTemplate.objects.get_or_create(
            vendor=data["vendor"],
            notification_type=data["notification_type"],
            channel=data["channel"],
            defaults={
                "subject": data["subject"],
                "body": data["body"],
                "is_active": data["is_active"],
            }
        )


class Migration(migrations.Migration):

    dependencies = [
        ('notification', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_system_notification_templates),
    ]
