from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction
from ..models import Assignment, Submission, Enrollment
from django.utils import timezone


@login_required
def assignment_detail_view(request, assignment_id):
    assignment = get_object_or_404(Assignment.objects.select_related("course", "module", "lesson"), id=assignment_id)

    # require enrollment if assignment tied to a course
    if assignment.course:
        enrollment = Enrollment.objects.filter(learner=request.user, course=assignment.course).first()
        if not enrollment:
            messages.error(request, "You must be enrolled to view this assignment.")
            return redirect("learn:course_detail", slug=assignment.course.slug)

    # learner's existing submission
    existing = Submission.objects.filter(assignment=assignment, learner=request.user).first() if request.user.is_authenticated else None

    return render(request, "learn/assignments/assignment_detail.html", {"assignment": assignment, "submission": existing})


@login_required
@transaction.atomic
def assignment_submit_view(request, assignment_id):
    assignment = get_object_or_404(Assignment, id=assignment_id)
    enrollment = None
    if assignment.course:
        enrollment = Enrollment.objects.filter(learner=request.user, course=assignment.course).first()
        if not enrollment:
            messages.error(request, "You must be enrolled to submit assignment.")
            return redirect("learn:course_detail", slug=assignment.course.slug)

    if request.method == "POST":
        content = request.POST.get("content", "")
        file = request.FILES.get("file") or None
        # allow update of existing submission
        submission, created = Submission.objects.update_or_create(
            assignment=assignment,
            learner=request.user,
            defaults={"content": content, "files": file, "submitted_at": timezone.now(), "status": "submitted"}
        )
        messages.success(request, "Assignment submitted successfully.")
        return redirect("learn:assignment_detail", assignment_id=assignment.id)

    return redirect("learn:assignment_detail", assignment_id=assignment.id)


# Instructor view for grading (basic permission check; adapt to your permission system)
def is_facilitator(user):
    return user.is_authenticated and hasattr(user, "facilitator_profile")

@login_required
@user_passes_test(is_facilitator)
def grade_submission_view(request, submission_id):
    submission = get_object_or_404(Submission.objects.select_related("assignment", "learner"), id=submission_id)
    if request.method == "POST":
        grade = request.POST.get("grade")
        feedback = request.POST.get("feedback", "")
        submission.grade = grade
        submission.feedback = feedback
        submission.grader = request.user
        submission.status = "graded"
        submission.save()
        messages.success(request, "Submission graded.")
        return redirect("learn:assignment_detail", assignment_id=submission.assignment.id)

    return render(request, "learn/assignments/grade_submission.html", {"submission": submission})
