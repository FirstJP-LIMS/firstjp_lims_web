from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.utils import timezone

from ..models import Lesson, Enrollment, LearnerProgress, LearnerProfile, MediaAsset


@login_required
def lesson_detail_view(request, lesson_id):
    """
    Render a lesson. Create or update LearnerProgress:
    - mark first_opened_at (if not set)
    - set started_at on first view
    """
    lesson = get_object_or_404(Lesson.objects.select_related("module__course"), id=lesson_id)
    course = lesson.module.course

    # ensure learner enrolled
    enrollment = Enrollment.objects.filter(learner=request.user, course=course).first()
    if not enrollment:
        messages.error(request, "You must be enrolled to access this lesson.")
        return redirect("learn:course_detail", slug=course.slug)

    progress, created = LearnerProgress.objects.get_or_create(enrollment=enrollment, lesson=lesson)

    # update timestamps and tracking
    changed = False
    now = timezone.now()
    if not progress.first_opened_at:
        progress.first_opened_at = now
        changed = True
    if not progress.started_at:
        progress.started_at = now
        changed = True
    if changed:
        progress.save(update_fields=["first_opened_at", "started_at", "updated_at"])

    # gather media assets to render player or document viewer
    media = lesson.media.all()

    context = {
        "lesson": lesson,
        "course": course,
        "module": lesson.module,
        "media": media,
        "progress": progress,
    }
    return render(request, "learn/lessons/lesson_detail.html", context)


@login_required
@transaction.atomic
def mark_lesson_complete_view(request, lesson_id):
    """
    Mark lesson as completed (can be called via POST/JS).
    Updates enrollment progress_percent atomically.
    """
    if request.method != "POST":
        return redirect("learn:lesson_detail", lesson_id=lesson_id)

    lesson = get_object_or_404(Lesson.objects.select_related("module__course"), id=lesson_id)
    course = lesson.module.course
    enrollment = Enrollment.objects.filter(learner=request.user, course=course).first()
    if not enrollment:
        messages.error(request, "You must be enrolled to complete this lesson.")
        return redirect("learn:course_detail", slug=course.slug)

    progress, _ = LearnerProgress.objects.get_or_create(enrollment=enrollment, lesson=lesson)

    if not progress.completed:
        progress.completed = True
        progress.completed_at = timezone.now()
        progress.save(update_fields=["completed", "completed_at", "updated_at"])

        # recompute enrollment progress_percent
        total_lessons = course.modules.prefetch_related("lessons").all()
        lesson_count = sum([m.lessons.count() for m in total_lessons])
        completed_count = enrollment.progress_items.filter(completed=True).count()
        progress_percent = 0
        if lesson_count > 0:
            progress_percent = round((completed_count / lesson_count) * 100, 2)
        enrollment.progress_percent = progress_percent
        if progress_percent >= 100:
            enrollment.status = "completed"
            enrollment.completed_at = timezone.now()
        enrollment.last_accessed_at = timezone.now()
        enrollment.save(update_fields=["progress_percent", "status", "completed_at", "last_accessed_at"])

    messages.success(request, f"Marked '{lesson.title}' as complete.")
    return redirect("learn:lesson_detail", lesson_id=lesson_id)
