# tasks.py
"""
Background tasks for automated result fetching.
Requires Celery to be configured in your Django project.
"""
from celery import shared_task
from django.utils import timezone
from datetime import timedelta
import logging

from .models import Equipment, TestAssignment
from .services import bulk_fetch_pending_results, InstrumentAPIError

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def poll_instrument_results(self, instrument_id):
    """
    Poll a specific instrument for pending results.
    Should be run periodically (e.g., every 5-10 minutes).
    """
    try:
        instrument = Equipment.objects.get(id=instrument_id, status='active')
        
        if not instrument.supports_auto_fetch:
            logger.info(f"Instrument {instrument.name} does not support auto-fetch")
            return
        
        # Fetch pending results
        count = bulk_fetch_pending_results(instrument, max_count=50)
        
        logger.info(f"Polled {instrument.name}: fetched {count} results")
        return count
        
    except Equipment.DoesNotExist:
        logger.error(f"Instrument {instrument_id} not found or inactive")
    except Exception as e:
        logger.error(f"Error polling instrument {instrument_id}: {e}")
        # Retry with exponential backoff
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))


@shared_task
def poll_all_instruments():
    """
    Poll all active instruments that support auto-fetch.
    Run this periodically (e.g., every 10 minutes).
    """
    instruments = Equipment.objects.filter(
        status='active',
        supports_auto_fetch=True,
        api_endpoint__isnull=False
    ).exclude(api_endpoint='')
    
    results = []
    for instrument in instruments:
        try:
            result = poll_instrument_results.delay(instrument.id)
            results.append({
                'instrument': instrument.name,
                'task_id': result.id
            })
        except Exception as e:
            logger.error(f"Failed to queue polling for {instrument.name}: {e}")
    
    return results


@shared_task
def retry_failed_submissions():
    """
    Retry sending assignments that failed to queue.
    Run this periodically (e.g., every 30 minutes).
    """
    from .services import send_assignment_to_instrument
    
    # Get assignments that failed to queue (retry_count > 0, status still Pending)
    failed_assignments = TestAssignment.objects.filter(
        status='P',
        retry_count__gt=0,
        retry_count__lt=5,  # Don't retry more than 5 times
        instrument__isnull=False,
        instrument__status='active'
    ).select_related('instrument')
    
    retried = 0
    for assignment in failed_assignments:
        try:
            send_assignment_to_instrument(assignment.id)
            retried += 1
        except InstrumentAPIError as e:
            logger.warning(f"Retry failed for assignment {assignment.id}: {e}")
            continue
    
    logger.info(f"Retried {retried} failed submissions")
    return retried


@shared_task
def alert_stale_assignments():
    """
    Alert on assignments that have been queued but not completed.
    Run this daily.
    """
    stale_threshold = timezone.now() - timedelta(hours=24)
    
    stale_assignments = TestAssignment.objects.filter(
        status__in=['Q', 'I'],
        queued_at__lt=stale_threshold
    ).select_related('request', 'lab_test', 'instrument')
    
    if stale_assignments.exists():
        # Send notifications (implement based on your notification system)
        logger.warning(f"Found {stale_assignments.count()} stale assignments")
        
        # Example: Send email to lab manager
        from django.core.mail import send_mail
        
        message = f"The following assignments have been pending for >24 hours:\n\n"
        for assignment in stale_assignments:
            message += f"- {assignment.request.request_id}: {assignment.lab_test.name}\n"
        
        # Uncomment to enable email alerts
        # send_mail(
        #     'Stale Test Assignments Alert',
        #     message,
        #     'noreply@yourlims.com',
        #     ['labmanager@yourlims.com'],
        #     fail_silently=True,
        # )
    
    return stale_assignments.count()


# Celery Beat Schedule (add to settings.py)
"""
CELERY_BEAT_SCHEDULE = {
    'poll-all-instruments': {
        'task': 'laboratory.tasks.poll_all_instruments',
        'schedule': crontab(minute='*/10'),  # Every 10 minutes
    },
    'retry-failed-submissions': {
        'task': 'laboratory.tasks.retry_failed_submissions',
        'schedule': crontab(minute='*/30'),  # Every 30 minutes
    },
    'alert-stale-assignments': {
        'task': 'laboratory.tasks.alert_stale_assignments',
        'schedule': crontab(hour=8, minute=0),  # Daily at 8 AM
    },
}
"""