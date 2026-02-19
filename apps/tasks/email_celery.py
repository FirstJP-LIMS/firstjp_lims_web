# apps/accounts/tasks.py (Celery Tasks for Async Processing)

"""
CELERY TASKS FOR SCALABLE EMAIL PROCESSING

WHY CELERY?
- Email sending can be slow (SMTP latency, network issues)
- Don't block HTTP request/response cycle waiting for email
- Retry mechanism for failed deliveries
- Background processing = better user experience

SETUP REQUIRED:
1. Install Celery: pip install celery redis
2. Configure Redis as message broker
3. Start Celery worker: celery -A config worker -l info
4. Start Celery beat (for scheduled tasks): celery -A config beat -l info

SCALABILITY BENEFITS:
- Handles 1,000+ concurrent password resets without blocking
- Automatic retry on email delivery failures
- Monitoring via Flower (celery -A config flower)
- Production: Use Amazon SES, SendGrid, or Mailgun for reliability
"""

from celery import shared_task
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from apps.tenants.models import Vendor
import logging
from django.utils import timezone
from datetime import timedelta

logger = logging.getLogger(__name__)
User = get_user_model()


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_password_reset_email(self, user_id, reset_url, tenant_id=None):
    """
    Send password reset email asynchronously.
    
    PARAMETERS:
    - user_id: Primary key of User model
    - reset_url: Full URL for password reset (includes uid & token)
    - tenant_id: Primary key of Vendor model (None for learning portal)
    
    RETRY LOGIC:
    - Retries up to 3 times on failure
    - 60 second delay between retries
    - Exponential backoff can be added
    
    MONITORING:
    - Log all attempts (success/failure)
    - Track delivery rates
    - Alert on persistent failures
    """
    try:
        # Fetch user and tenant
        user = User.objects.get(id=user_id)
        tenant = None
        
        if tenant_id:
            tenant = Vendor.objects.get(id=tenant_id)
        
        # Prepare email context
        context = {
            'user': user,
            'reset_url': reset_url,
            'tenant': tenant,
            'vendor_name': tenant.name if tenant else 'MedVuno Learning Portal',
            'valid_hours': 24,
            'support_email': settings.DEFAULT_FROM_EMAIL,
        }
        
        # Render email templates
        email_body_html = render_to_string(
            'authentication/password_reset/password_reset_email.html',
            context
        )
        
        email_body_text = render_to_string(
            'authentication/password_reset/password_reset_email.txt',
            context
        )
        
        email_subject = f"Password Reset Request - {context['vendor_name']}"
        
        # Send email
        send_mail(
            subject=email_subject,
            message=email_body_text,
            html_message=email_body_html,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
        
        logger.info(
            f"Password reset email sent successfully: "
            f"User={user.email}, Tenant={tenant}, Task ID={self.request.id}"
        )
        
        return {
            'status': 'success',
            'user_email': user.email,
            'tenant': str(tenant) if tenant else 'Learning Portal'
        }
    
    except User.DoesNotExist:
        logger.error(f"User with ID {user_id} not found. Task ID: {self.request.id}")
        return {'status': 'error', 'message': 'User not found'}
    
    except Exception as exc:
        logger.error(
            f"Failed to send password reset email: {str(exc)}. "
            f"Task ID: {self.request.id}. Retrying..."
        )
        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_password_changed_notification(self, user_id):
    """
    Send notification that password was changed.
    
    SECURITY PURPOSE:
    - Alert user of password change
    - Helps detect unauthorized access
    - Provides contact info for reporting issues
    
    ASYNC PROCESSING:
    - Doesn't block password reset completion
    - Retries on delivery failure
    """
    try:
        user = User.objects.get(id=user_id)
        tenant = user.vendor
        
        context = {
            'user': user,
            'tenant': tenant,
            'vendor_name': tenant.name if tenant else 'MedVuno Platform',
            'support_email': settings.DEFAULT_FROM_EMAIL,
            'timestamp': timezone.now(),
        }
        
        email_body_html = render_to_string(
            'authentication/password_reset/password_changed_notification.html',
            context
        )
        
        email_body_text = render_to_string(
            'authentication/password_reset/password_changed_notification.txt',
            context
        )
        
        send_mail(
            subject=f"Your Password Was Changed - {context['vendor_name']}",
            message=email_body_text,
            html_message=email_body_html,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
        
        logger.info(
            f"Password changed notification sent: "
            f"User={user.email}, Task ID={self.request.id}"
        )
        
        return {'status': 'success', 'user_email': user.email}
    
    except User.DoesNotExist:
        logger.error(f"User with ID {user_id} not found. Task ID: {self.request.id}")
        return {'status': 'error', 'message': 'User not found'}
    
    except Exception as exc:
        logger.error(
            f"Failed to send password changed notification: {str(exc)}. "
            f"Task ID: {self.request.id}"
        )
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@shared_task
def send_welcome_email(user_id):
    """
    Send welcome email after user registration.
    
    TRIGGERED BY:
    - New user registration (all roles)
    - Email verification (if enabled)
    
    CONTENT:
    - Welcome message
    - Getting started guide
    - Support contact info
    - Role-specific instructions
    """
    try:
        user = User.objects.get(id=user_id)
        tenant = user.vendor
        
        # Role-specific welcome content
        role_guides = {
            'patient': 'Check your test results, book appointments, and manage your health records.',
            'clinician': 'Order tests for your patients and receive results securely.',
            'lab_staff': 'Process samples, enter results, and manage lab operations.',
            'vendor_admin': 'Configure your lab settings and manage staff accounts.',
            'learner': 'Explore courses and start your learning journey.',
            'facilitator': 'Create and manage courses for your learners.',
        }
        
        context = {
            'user': user,
            'tenant': tenant,
            'vendor_name': tenant.name if tenant else 'MedVuno',
            'role_guide': role_guides.get(user.role, 'Welcome to the platform!'),
            'login_url': settings.SITE_URL + '/accounts/login/',
        }
        
        email_body = render_to_string(
            'authentication/emails/welcome_email.html',
            context
        )
        
        send_mail(
            subject=f"Welcome to {context['vendor_name']}!",
            message='',
            html_message=email_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=True,
        )
        
        logger.info(f"Welcome email sent to {user.email}")
    
    except Exception as e:
        logger.error(f"Failed to send welcome email: {str(e)}")


# ============================================================================
# CELERY CONFIGURATION (config/celery.py)
# ============================================================================

"""
# config/celery.py

import os
from celery import Celery

# Set default Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# Create Celery app
app = Celery('medvuno_lims')

# Load configuration from Django settings (prefix: CELERY_)
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks in all installed apps
app.autodiscover_tasks()

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')


# ============================================================================
# DJANGO SETTINGS (config/settings.py)
# ============================================================================

# Celery Configuration
CELERY_BROKER_URL = 'redis://localhost:6379/0'  # Redis as message broker
CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'  # Store task results
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'

# Email retry settings
CELERY_TASK_MAX_RETRIES = 3
CELERY_TASK_DEFAULT_RETRY_DELAY = 60  # seconds

# Task result expiration
CELERY_RESULT_EXPIRES = 3600  # 1 hour


# Email Configuration (Production)
# Use environment variables for security
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.sendgrid.net')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', 587))
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'noreply@medvuno.com')

# Frontend URL (for REST API password reset links)
FRONTEND_URL = os.getenv('FRONTEND_URL', 'https://app.medvuno.com')


# ============================================================================
# DOCKER COMPOSE (docker-compose.yml) - For Production
# ============================================================================

version: '3.8'

services:
  # Django application
  web:
    build: .
    command: gunicorn config.wsgi:application --bind 0.0.0.0:8000
    volumes:
      - .:/app
    ports:
      - "8000:8000"
    depends_on:
      - db
      - redis
    environment:
      - DATABASE_URL=postgresql://user:password@db:5432/medvuno
      - CELERY_BROKER_URL=redis://redis:6379/0
      - EMAIL_HOST_USER=${EMAIL_HOST_USER}
      - EMAIL_HOST_PASSWORD=${EMAIL_HOST_PASSWORD}
  
  # PostgreSQL database
  db:
    image: postgres:15
    volumes:
      - postgres_data:/var/lib/postgresql/data
    environment:
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=password
      - POSTGRES_DB=medvuno
  
  # Redis (Celery broker)
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
  
  # Celery worker
  celery:
    build: .
    command: celery -A config worker -l info
    volumes:
      - .:/app
    depends_on:
      - db
      - redis
    environment:
      - CELERY_BROKER_URL=redis://redis:6379/0
      - DATABASE_URL=postgresql://user:password@db:5432/medvuno
  
  # Celery beat (scheduled tasks)
  celery-beat:
    build: .
    command: celery -A config beat -l info
    volumes:
      - .:/app
    depends_on:
      - redis
    environment:
      - CELERY_BROKER_URL=redis://redis:6379/0
  
  # Flower (Celery monitoring)
  flower:
    build: .
    command: celery -A config flower
    ports:
      - "5555:5555"
    depends_on:
      - redis
      - celery
    environment:
      - CELERY_BROKER_URL=redis://redis:6379/0

volumes:
  postgres_data:
"""