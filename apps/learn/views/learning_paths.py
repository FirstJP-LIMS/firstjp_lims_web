from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import login_required

from ..models import LearningPath, LearningPathProgress


def learning_path_list_view(request):
    paths = LearningPath.objects.filter(published=True).order_by("title")
    return render(request, "learn/paths/path_list.html", {"paths": paths})


def learning_path_detail_view(request, slug):
    path = get_object_or_404(LearningPath.objects.prefetch_related("path_courses__course"), slug=slug)
    courses_ordered = [pc.course for pc in path.path_courses.order_by("position").select_related("course")]
    return render(request, "learn/paths/path_detail.html", {"path": path, "courses": courses_ordered})


@login_required
def learning_path_enroll_view(request, slug):
    path = get_object_or_404(LearningPath, slug=slug, published=True)
    progress, created = LearningPathProgress.objects.get_or_create(learner=request.user, learning_path=path)
    if created:
        messages.success(request, f"You are enrolled in the learning path: {path.title}")
    else:
        messages.info(request, f"You are already enrolled in {path.title}")
    return redirect("learn:learning_path_detail", slug=path.slug)
