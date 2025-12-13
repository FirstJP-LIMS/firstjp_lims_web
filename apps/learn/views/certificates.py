from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import get_random_string

from ..models import Enrollment, Certificate


@login_required
def certificate_view(request, enrollment_id):
    enrollment = get_object_or_404(Enrollment.objects.select_related("course"), id=enrollment_id, learner=request.user)
    certificate = getattr(enrollment, "certificate", None)
    return render(request, "learn/certificates/certificate_detail.html", {"enrollment": enrollment, "certificate": certificate})


@login_required
@transaction.atomic
def generate_certificate_view(request, enrollment_id):
    """
    Basic certificate generation (creates database record).
    You likely want a separate PDF generation pipeline (WeasyPrint / ReportLab / external service).
    """
    enrollment = get_object_or_404(Enrollment.objects.select_related("course"), id=enrollment_id, learner=request.user)

    if enrollment.status != "completed":
        messages.error(request, "You must complete the course to claim a certificate.")
        return redirect("learn:course_detail", slug=enrollment.course.slug)

    if hasattr(enrollment, "certificate") and enrollment.certificate is not None:
        messages.info(request, "A certificate already exists for this enrollment.")
        return redirect("learn:certificate_detail", enrollment_id=enrollment.id)

    certificate_id = f"{enrollment.course.slug.upper()}-{get_random_string(8).upper()}"
    cert = Certificate.objects.create(
        enrollment=enrollment,
        certificate_name=f"Certificate of Completion — {enrollment.course.title}",
        certificate_id=certificate_id,
        issued_at=timezone.now(),
    )

    # TODO: enqueue PDF creation job to generate cert.pdf and attach path to cert.pdf
    messages.success(request, "Certificate claimed. PDF generation may complete shortly.")
    return redirect("learn:certificate_detail", enrollment_id=enrollment.id)

