from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import login_required

from ..models import Course, Lesson, DiscussionThread, DiscussionReply


def thread_list_view(request, course_slug, lesson_id=None):
    course = get_object_or_404(Course, slug=course_slug)
    threads = DiscussionThread.objects.filter(course=course, is_deleted=False).order_by("-pinned", "-created_at")
    if lesson_id:
        threads = threads.filter(lesson_id=lesson_id)
    return render(request, "learn/discussions/thread_list.html", {"course": course, "threads": threads})


@login_required
def thread_create_view(request, course_slug, lesson_id=None):
    course = get_object_or_404(Course, slug=course_slug)
    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        body = request.POST.get("body", "").strip()
        if not title or not body:
            messages.error(request, "Title and body are required.")
            return redirect("learn:thread_list", course_slug=course.slug)
        thread = DiscussionThread.objects.create(
            course=course,
            lesson_id=lesson_id,
            created_by=request.user,
            title=title,
            body=body
        )
        messages.success(request, "Discussion thread created.")
        return redirect("learn:thread_detail", thread_id=thread.id)

    return render(request, "learn/discussions/thread_create.html", {"course": course, "lesson_id": lesson_id})


@login_required
def reply_create_view(request, thread_id):
    thread = get_object_or_404(DiscussionThread, id=thread_id, is_deleted=False)
    if request.method == "POST":
        body = request.POST.get("body", "").strip()
        parent_id = request.POST.get("parent")
        if not body:
            messages.error(request, "Reply body is required.")
            return redirect("learn:thread_detail", thread_id=thread.id)

        reply = DiscussionReply.objects.create(thread=thread, created_by=request.user, body=body, parent_id=parent_id or None)
        messages.success(request, "Reply posted.")
        return redirect("learn:thread_detail", thread_id=thread.id)

    return redirect("learn:thread_detail", thread_id=thread.id)
