# LIMS Instrument Integration - Deployment Guide

## Overview
This system integrates Django LIMS with Windows-based laboratory instruments via REST API.

## Key Features
✅ Send tests to instruments automatically  
✅ Fetch results from instruments (manual or automated polling)  
✅ Manual result entry with validation  
✅ Multi-level verification workflow  
✅ Complete audit trail  
✅ Multi-tenant security  
✅ Retry logic for failed submissions  
✅ Background tasks for result polling  

---

## Installation Steps

### 1. Install Dependencies

```bash
pip install requests celery redis
```

### 2. Update Django Settings

```python
# settings.py

# Instrument API Configuration
INSTRUMENT_API_TIMEOUT = 10  # seconds

# Celery Configuration (for background tasks)
CELERY_BROKER_URL = 'redis://localhost:6379/0'
CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'Africa/Lagos'

# Celery Beat Schedule
from celery.schedules import crontab

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

# Logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': 'lims_instrument.log',
        },
    },
    'loggers': {
        'laboratory': {
            'handlers': ['file'],
            'level': 'INFO',
            'propagate': True,
        },
    },
}
```

### 3. Create Celery App

```python
# your_project/celery.py
import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'your_project.settings')

app = Celery('your_project')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
```

```python
# your_project/__init__.py
from .celery import app as celery_app

__all__ = ('celery_app',)
```

### 4. Run Migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

### 5. Configure Equipment

In Django Admin or shell:

```python
from laboratory.models import Equipment

# Create instrument
instrument = Equipment.objects.create(
    vendor=your_vendor,
    name="Hematology Analyzer XYZ",
    model="Model-2000",
    serial_number="SN123456",
    department=hematology_dept,
    api_endpoint="http://windows-lims.local:8080",
    api_key="your-api-key-here",
    supports_auto_fetch=True,
    status='active'
)
```

---

## Windows LIMS API Specification

### Expected Payload Format

#### Sending Test to Instrument (POST /api/queue)

```json
{
  "id": 0,
  "patientId": "PAT-001",
  "testName": "CBC",
  "testCode": "LAB-CBC",
  "sampleId": "SAMP-123",
  "requestId": "REQ-456",
  "priority": "routine",
  "specimenType": "Blood",
  "metadata": {
    "assignmentId": 789,
    "vendorId": 1,
    "departmentId": 3
  }
}
```

**Expected Response:**

```json
{
  "id": 12345,
  "status": "queued",
  "queuePosition": 3
}
```

#### Fetching Result (GET /api/results/{id})

**Expected Response:**

```json
{
  "id": 12345,
  "patientId": "PAT-001",
  "testName": "CBC",
  "value": "12.5",
  "unit": "g/dL",
  "status": "completed",
  "remarks": "",
  "qualityControl": "Passed",
  "completedAt": "2025-11-12T10:30:00Z"
}
```

#### Checking Instrument Status (GET /api/status)

**Expected Response:**

```json
{
  "status": "online",
  "queueLength": 5,
  "lastCalibration": "2025-11-10T08:00:00Z"
}
```

---

## Usage Workflow

### Manual Workflow

1. **Create Test Assignment** → Status: `Pending (P)`
2. **Send to Instrument** → Status: `Queued (Q)`
3. **Fetch Result** → Status: `Analysis Complete (A)`
4. **Verify Result** → Status: `Verified (V)`
5. **Release Result** → Patient receives report

### Automated Workflow

1. **Create Test Assignment** → Status: `Pending (P)`
2. **Send to Instrument** → Status: `Queued (Q)`
3. **Background Task Polls Instrument** → Auto-fetches when ready
4. **Result Saved** → Status: `Analysis Complete (A)`
5. **Lab Tech Verifies** → Status: `Verified (V)`
6. **Release Result** → Patient receives report

---

## Running Background Tasks

### Start Celery Worker

```bash
celery -A your_project worker --loglevel=info
```

### Start Celery Beat (Scheduler)

```bash
celery -A your_project beat --loglevel=info
```

### For Production (with supervisor)

```ini
# /etc/supervisor/conf.d/celery.conf
[program:celery]
command=/path/to/venv/bin/celery -A your_project worker --loglevel=info
directory=/path/to/project
user=www-data
autostart=true
autorestart=true
stdout_logfile=/var/log/celery/worker.log
stderr_logfile=/var/log/celery/worker.error.log

[program:celerybeat]
command=/path/to/venv/bin/celery -A your_project beat --loglevel=info
directory=/path/to/project
user=www-data
autostart=true
autorestart=true
stdout_logfile=/var/log/celery/beat.log
stderr_logfile=/var/log/celery/beat.error.log
```

---

## Security Considerations

### 1. API Authentication
- Store API keys in environment variables, not in code
- Use Django's encrypted fields for sensitive data
- Implement token rotation

```python
# settings.py
INSTRUMENT_API_KEYS = {
    'instrument_1': os.getenv('INSTRUMENT_1_API_KEY'),
    'instrument_2': os.getenv('INSTRUMENT_2_API_KEY'),
}
```

### 2. Multi-Tenant Isolation
- Always filter by `vendor` in queries
- Use middleware to enforce tenant boundaries
- Audit all cross-tenant access attempts

### 3. HTTPS Only
- Ensure all instrument APIs use HTTPS in production
- Validate SSL certificates

---

## Troubleshooting

### Issue: Results not being fetched automatically

**Check:**
1. Is Celery worker running? `ps aux | grep celery`
2. Is Redis running? `redis-cli ping`
3. Is `supports_auto_fetch` enabled on instrument?
4. Check logs: `tail -f lims_instrument.log`

### Issue: "Cannot send to instrument"

**Check:**
1. Is instrument status `active`?
2. Is `api_endpoint` configured?
3. Is assignment in `Pending` status?
4. Test connection manually: `curl http://windows-lims.local/api/status`

### Issue: Timeout errors

**Increase timeout in settings:**
```python
INSTRUMENT_API_TIMEOUT = 30  # Increase to 30 seconds
```

---

## Testing

### Manual Testing

```python
# Django shell
from laboratory.models import TestAssignment
from laboratory.services import send_assignment_to_instrument

assignment = TestAssignment.objects.get(id=123)
result = send_assignment_to_instrument(assignment.id)
print(result)
```

### Unit Tests

```python
# tests.py
from django.test import TestCase
from unittest.mock import patch, MagicMock
from laboratory.services import InstrumentService

class InstrumentIntegrationTests(TestCase):
    @patch('requests.post')
    def test_send_to_instrument(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {'id': 12345}
        
        # Test sending assignment
        # ... your test code
```

---

## Monitoring

### Key Metrics to Track

1. **Instrument uptime** - Track via status checks
2. **Average turnaround time** - From queued to completed
3. **Failed submissions** - Monitor retry counts
4. **Stale assignments** - Tests pending >24 hours

### Dashboard Queries

```python
# Get pending assignments count
pending_count = TestAssignment.objects.filter(
    vendor=vendor,
    status__in=['P', 'Q', 'I']
).count()

# Get average TAT
from django.db.models import Avg, F
avg_tat = TestAssignment.objects.filter(
    analyzed_at__isnull=False
).aggregate(
    avg_time=Avg(F('analyzed_at') - F('queued_at'))
)
```

---

## Support & Documentation

- **API Documentation**: Check Windows LIMS vendor documentation
- **Django LIMS**: Internal documentation
- **Celery Docs**: https://docs.celeryproject.org/

## Notes for Windows LIMS Team

When integrating with your system, please ensure:
1. Your API supports the payload formats specified above
2. Authentication headers are consistent
3. Error responses include meaningful messages
4. Status endpoints are publicly accessible (or use auth)
5. Results remain available for at least 24 hours after completion
