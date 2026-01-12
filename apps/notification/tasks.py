# apps/notifications/tasks.py
from celery import shared_task
from .domain_events import DomainEvent
from .channels import email, sms
import json

@shared_task
def send_email_task(event_data):
    """
    Celery task to send email notifications.
    """
    event = DomainEvent(**event_data)
    email.send_notification(event)

@shared_task
def send_sms_task(event_data):
    """
    Celery task to send SMS notifications.
    """
    event = DomainEvent(**event_data)
    sms.send_notification(event)

