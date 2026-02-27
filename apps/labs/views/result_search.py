"""
apps/lab/views/result_search.py

Public-facing result search view.
- No authentication required
- Tenant resolved from request.tenant (set by TenantMiddleware)
- Rate limited by IP: 10 requests per 10 minutes
- Two-factor patient lookup: patient_id + date_of_birth
- Returns only released/amended results, grouped by TestRequest
"""


import logging
from datetime import datetime

from django.shortcuts import render, redirect
from django.views import View
from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit
from django.db.models import Prefetch

from ..models import Patient, TestRequest, TestAssignment, TestResult

logger = logging.getLogger(__name__)

RESULT_LIMIT = 10   # Most recent N requests shown per search
RATE = '10/10m'     # 10 searches per 10 minutes per IP


# ── Helpers ────────────────────────────────────────────────────────────────────

def _parse_dob(raw: str):
    """
    Attempt to parse a date of birth string from common input formats.
    Returns a date object, or None if all formats fail.
    """
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'):
        try:
            return datetime.strptime(raw.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _get_client_ip(request):
    """
    Extract the real client IP address.
    Respects X-Forwarded-For when behind a reverse proxy.
    """
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', 'unknown')


def _build_result_groups(requests_qs):
    """
    Iterate prefetched TestRequests and group their released/amended
    TestResults into a clean list of dicts for the template.

    Structure returned:
        [
            {
                'request': <TestRequest>,
                'results': [<TestResult>, ...],
            },
            ...
        ]

    Any request with zero eligible results is silently excluded
    (acts as a safety net if the queryset filter behaves unexpectedly).
    """
    groups = []

    for req in requests_qs:
        eligible_results = []

        for assignment in req.assignments.all():
            # result is a OneToOneField — may not exist on every assignment
            result = getattr(assignment, 'result', None)
            if result and result.status in ('released', 'amended'):
                eligible_results.append(result)

        if eligible_results:
            groups.append({
                'request': req,
                'results': eligible_results,
            })

    return groups


# ── View ───────────────────────────────────────────────────────────────────────

# System Error: 'Patient' object has no attribute 'email'

@method_decorator(
    ratelimit(key='ip', rate=RATE, method='POST', block=True),
    name='dispatch',
)
class ResultSearchView(View):
    """
    Public result search — no login required.

    GET  → renders the empty search form.
    POST → validates input, performs two-factor patient lookup,
           and returns grouped released/amended results on the same page.
    """

    TEMPLATE = 'laboratory/public/result_search.html'

    # ── GET ────────────────────────────────────────────────────────────

    def get(self, request):
        if not request.tenant:
            return redirect('/')

        return render(request, self.TEMPLATE, {
            'searched': False,
        })

    # ── POST ───────────────────────────────────────────────────────────

    def post(self, request):
        vendor = request.tenant
        if not vendor:
            return redirect('/')

        patient_id_raw = request.POST.get('patient_id', '').strip().upper()
        dob_raw = request.POST.get('date_of_birth', '').strip()

        # ── 1. Input validation ────────────────────────────────────────
        errors = {}

        if not patient_id_raw:
            errors['patient_id'] = 'Patient ID is required.'

        dob = None
        if not dob_raw:
            errors['date_of_birth'] = 'Date of birth is required.'
        else:
            dob = _parse_dob(dob_raw)
            if dob is None:
                errors['date_of_birth'] = 'Enter a valid date (YYYY-MM-DD or DD/MM/YYYY).'

        if errors:
            return render(request, self.TEMPLATE, {
                'searched': True,
                'found': False,
                'errors': errors,
                'patient_id': patient_id_raw,
                'date_of_birth': dob_raw,
            })

        # ── 2. Patient lookup ──────────────────────────────────────────
        #
        # IMPORTANT: We use ONE generic error message for all failure
        # cases (wrong ID, wrong DOB, or patient doesn't exist in this
        # tenant). Never differentiate — doing so would allow enumeration
        # of valid patient IDs.
        #
        try:
            patient = Patient.objects.get(
                vendor=vendor,
                patient_id=patient_id_raw,
                date_of_birth=dob,
            )
        except Patient.DoesNotExist:
            logger.info(
                "Result search miss | vendor=%s | input_id=%s | ip=%s",
                vendor.tenant_id,
                patient_id_raw,
                _get_client_ip(request),
            )
            return render(request, self.TEMPLATE, {
                'searched': True,
                'found': False,
                'patient_id': patient_id_raw,
                'date_of_birth': dob_raw,
            })

        # ── 3. Fetch released/amended results ──────────────────────────
        #
        # Strategy: find TestRequests that have at least one
        # released/amended result, then prefetch those assignments
        # and results efficiently to avoid N+1 queries.
        #
        released_results_prefetch = Prefetch(
            'result',
            queryset=TestResult.objects.filter(
                status__in=['released', 'amended']
            ).select_related(
                'assignment__lab_test',
                'ai_insight',          # OneToOne — may not exist, guarded in template
            ),
        )

        assignments_prefetch = Prefetch(
            'assignments',
            queryset=TestAssignment.objects.select_related(
                'lab_test',
                'sample',
                'department',
            ).prefetch_related(released_results_prefetch),
        )

        requests_qs = (
            TestRequest.objects
            .filter(
                vendor=vendor,
                patient=patient,
                # Only include requests that have at least one
                # released/amended result — avoids returning
                # empty request cards to the patient
                assignments__result__status__in=['released', 'amended'],
            )
            .distinct()
            .order_by('-created_at')
            .prefetch_related(assignments_prefetch)
            [:RESULT_LIMIT]
        )

        result_groups = _build_result_groups(requests_qs)

        logger.info(
            "Result search hit | vendor=%s | patient=%s | request_groups=%d | ip=%s",
            vendor.tenant_id,
            patient.patient_id,
            len(result_groups),
            _get_client_ip(request),
        )

        return render(request, self.TEMPLATE, {
            'searched': True,
            'found': bool(result_groups),
            'patient': patient,
            'result_groups': result_groups,
            'patient_id': patient_id_raw,
            'date_of_birth': dob_raw,
        })

