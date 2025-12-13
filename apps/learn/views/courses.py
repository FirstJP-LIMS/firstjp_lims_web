from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import login_required
from django.urls import reverse

from ..models import Course, Module, Enrollment, LearningPathProgress, LearnerProgress


def course_list_view(request):
    """Public listing of published courses with pagination."""
    queryset = Course.objects.filter(published=True).select_related('category').prefetch_related('tags')
    q = request.GET.get('q')
    if q:
        queryset = queryset.filter(title__icontains=q)  # basic search; replace with full-text search if desired

    paginator = Paginator(queryset, 12)
    page = request.GET.get('page')
    courses = paginator.get_page(page)
    return render(request, "learn/courses/course_list.html", {"courses": courses, "q": q})


def course_detail_view(request, slug):
    """Course detail page. Shows modules, enroll button, and progress for authenticated learners."""
    course = get_object_or_404(Course.objects.prefetch_related(
        Prefetch("modules", queryset=Module.objects.order_by("position").all())
    ), slug=slug)

    user_enrollment = None
    progress = None
    if request.user.is_authenticated:
        user_enrollment = Enrollment.objects.filter(learner=request.user, course=course).first()
        if user_enrollment:
            # fetch course-level progress or per-lesson summary as needed
            progress = {
                "progress_percent": user_enrollment.progress_percent,
                "completed_at": user_enrollment.completed_at,
            }

    context = {
        "course": course,
        "enrollment": user_enrollment,
        "progress": progress,
    }
    return render(request, "learn/courses/course_detail.html", context)


@login_required
def enroll_in_course_view(request, course_slug):
    """Enroll the logged-in learner into a course (idempotent)."""
    course = get_object_or_404(Course, slug=course_slug, published=True)
    enrollment, created = Enrollment.objects.get_or_create(learner=request.user, course=course)
    if created:
        messages.success(request, f"You are now enrolled in {course.title}.")
    else:
        messages.info(request, f"You are already enrolled in {course.title}.")

    return redirect("learn:course_detail", slug=course.slug)


@login_required
def continue_course_view(request, course_slug):
    """
    Redirect learner to last-unfinished lesson for a course;
    fallback to first lesson in the first module.
    """
    course = get_object_or_404(Course, slug=course_slug, published=True)
    enrollment = Enrollment.objects.filter(learner=request.user, course=course).first()
    if not enrollment:
        messages.info(request, "You are not enrolled in this course.")
        return redirect("learn:course_detail", slug=course.slug)

    # Find last incomplete lesson: check LearnerProgress
    last_progress = (
        LearnerProgress.objects.filter(enrollment=enrollment)
        .order_by("-updated_at")
        .first()
    )

    if last_progress and not last_progress.completed:
        lesson = last_progress.lesson
    else:
        # first required lesson in first module
        first_module = course.modules.order_by("position").first()
        lesson = None
        if first_module:
            lesson = first_module.lessons.order_by("position").first()

    if not lesson:
        messages.error(request, "No lessons are available for this course.")
        return redirect("learn:course_detail", slug=course.slug)

    return redirect("learn:lesson_detail", lesson_id=lesson.id)
