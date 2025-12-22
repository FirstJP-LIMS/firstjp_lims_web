from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Prefetch, Avg
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import login_required
from django.urls import reverse

from ..models import Course, Module, Enrollment, LearningPathProgress, LearnerProgress, CourseCategory, CourseTag, CourseFeedback, Lesson, Enrollment, CourseFeedback
from ..services.currency import get_user_currency, attach_display_price


def course_list_view(request):
    """
    Public listing of published courses with pagination,
    filtering, search, and regional pricing.
    """

    currency_code, currency_symbol, country_code = get_user_currency(request)

    queryset = (
        Course.objects
        .filter(published=True)
        .select_related("category")
        .prefetch_related("tags")
        .annotate(avg_rating=Avg("feedbacks__rating"))
        .order_by("-featured", "-published_at")
    )

    q = request.GET.get("q")
    category_slug = request.GET.get("category")
    tag_name = request.GET.get("tag")

    if q:
        queryset = queryset.filter(title__icontains=q)

    if category_slug:
        queryset = queryset.filter(category__slug=category_slug)

    if tag_name:
        queryset = queryset.filter(tags__name=tag_name)

    paginator = Paginator(queryset, 12)
    page_obj = paginator.get_page(request.GET.get("page"))

    # Attach prices AFTER pagination
    for course in page_obj:
        attach_display_price(course, currency_code, currency_symbol)

    context = {
        "courses": page_obj,
        "categories": CourseCategory.objects.all(),
        "tags": CourseTag.objects.all(),
        "q": q,
        "selected_category": category_slug,
        "selected_tag": tag_name,
        "currency_code": currency_code,
        "country_code": country_code,
    }

    return render(request, "learn/courses/course_list.html", context)


def course_detail_view(request, slug):
    """
    Public course detail page.
    Displays curriculum, rating, and enrollment state.
    """

    course = get_object_or_404(
        Course.objects.filter(published=True)
        .prefetch_related(
            Prefetch(
                "modules",
                queryset=Module.objects.order_by("position").prefetch_related(
                    Prefetch(
                        "lessons",
                        queryset=Lesson.objects.order_by("position")
                    )
                )
            ),
            "facilitators"
        )
        .annotate(avg_rating=Avg("feedbacks__rating")),
        slug=slug
    )

    enrollment = None
    progress = None

    if request.user.is_authenticated:
        enrollment = Enrollment.objects.filter(
            learner=request.user,
            course=course
        ).first()

        if enrollment:
            progress = {
                "percent": enrollment.progress_percent,
                "completed_at": enrollment.completed_at,
                "status": enrollment.status,
            }

    context = {
        "course": course,
        "enrollment": enrollment,
        "progress": progress,
        "modules": course.modules.all(),
        "avg_rating": course.avg_rating,
        "feedback_count": CourseFeedback.objects.filter(course=course).count(),
    }

    return render(request, "learn/courses/course_detail.html", context)


@login_required
def enroll_in_course_view(request, slug):
    course = get_object_or_404(Course, slug=slug, published=True)
    # Paid course gate
    if not course.is_free:
        messages.warning(
            request,
            "This is a paid course. Payment is required before enrollment."
        )
        return redirect("learn:course_detail", slug=course.slug)

    enrollment, created = Enrollment.objects.get_or_create(
        learner=request.user,
        course=course
    )

    if created:
        messages.success(request, f"You are now enrolled in {course.title}.")
    else:
        messages.info(request, "You are already enrolled in this course.")

    return redirect("learn:continue_course", slug=course.slug)


@login_required
def continue_course_view(request, slug):
    course = get_object_or_404(Course, slug=slug, published=True)

    enrollment = Enrollment.objects.filter(
        learner=request.user,
        course=course,
        status='active'
    ).first()

    if not enrollment:
        return redirect("learn:course_detail", slug=slug)

    last_progress = (
        LearnerProgress.objects
        .filter(enrollment=enrollment, completed=False)
        .select_related("lesson")
        .order_by("lesson__position")
        .first()
    )

    if last_progress:
        return redirect("learn:lesson_detail", lesson_id=last_progress.lesson.id)

    # fallback → first lesson
    first_module = course.modules.order_by("position").first()
    if not first_module:
        return redirect("learn:course_detail", slug=slug)

    first_lesson = first_module.lessons.order_by("position").first()
    if not first_lesson:
        return redirect("learn:course_detail", slug=slug)

    return redirect("learn:lesson_detail", lesson_id=first_lesson.id)

