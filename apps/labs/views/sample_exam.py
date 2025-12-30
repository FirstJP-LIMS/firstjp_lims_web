import json
import logging
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from functools import wraps

# Django Core
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import (
    Avg, Count, DurationField, ExpressionWrapper, F, Q, Sum, Prefetch
)
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

# App-Specific Imports
from apps.accounts.models import VendorProfile
from apps.tenants.models import Vendor

from ..forms import (
    DepartmentForm,
    SampleForm,
    TestRequestForm,
    VendorLabTestForm
)
from ..models import (
    AuditLog,
    Department,
    Equipment,
    Patient,
    QualitativeOption,
    Sample,
    TestAssignment,
    TestRequest,
    TestResult,
    VendorTest
)
from ..services import (
    InstrumentAPIError,
    InstrumentService,
    fetch_assignment_result,
    send_assignment_to_instrument
)
from ..utils import check_tenant_access

from ..decorators import lab_supervisor_required, lab_technician_required


# Logger Setup
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


# **************
# Phase 2: Sample Examination                 
# **************
@login_required
def sample_examination_list(request):
    """List all samples awaiting verification or processing."""
    samples = Sample.objects.filter(status__in=['AC', 'RJ', 'AP']).select_related('patient', 'test_request')
    return render(request, 'laboratory/examination/sample_list.html', {'samples': samples})

@login_required
def sample_examination_detail(request, sample_id):
    """Detail view for verifying a specific sample."""
    sample = get_object_or_404(
        Sample.objects.select_related('test_request','test_request__patient', 'vendor'
        ).prefetch_related('test_request__requested_tests'),
        sample_id=sample_id
    )

    if request.method == 'POST':
        action = request.POST.get('action')
        reason = request.POST.get('reason', '')

        # Technician actions
        if action == 'verify':
            sample.verify_sample(request.user)
            messages.success(request, f"Sample {sample.sample_id} has been verified successfully.")
            return redirect(reverse('labs:sample-exam-detail', args=[sample.sample_id]))

        elif action == 'accept':
            sample.accept_sample(request.user)
            messages.success(request, f"Sample {sample.sample_id} accepted and queued for analysis.")
            return redirect('labs:sample-exam-list')

        elif action == 'reject':
            sample.reject_sample(request.user, reason)
            messages.warning(request, f"Sample {sample.sample_id} rejected.")
            return redirect('labs:sample-exam-list')

    return render(request, 'laboratory/examination/sample_detail.html', {'sample': sample})


