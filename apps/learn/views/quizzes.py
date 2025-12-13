import json
from decimal import Decimal
from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import login_required
from django.utils import timezone

from ..models import Quiz, Question, Option, LearnerQuizAttempt, Enrollment


@login_required
def quiz_view(request, quiz_id):
    """Show quiz (questions). If time-limited, front-end should enforce time."""
    quiz = get_object_or_404(Quiz.objects.prefetch_related("questions__options"), id=quiz_id)

    # If quiz is attached to a lesson, ensure user is enrolled in course
    if quiz.lesson:
        course = quiz.lesson.module.course
    elif quiz.module:
        course = quiz.module.course
    else:
        course = None

    if course:
        enrollment = Enrollment.objects.filter(learner=request.user, course=course).first()
        if not enrollment:
            messages.error(request, "You must be enrolled to take this quiz.")
            return redirect("learn:course_detail", slug=course.slug)

    return render(request, "learn/quizzes/quiz_detail.html", {"quiz": quiz})


@login_required
@transaction.atomic
def quiz_submit_view(request, quiz_id):
    """
    Process quiz submission:
    - Accept JSON payload or form-encoded answers
    - Grade MCQ/multi/tf automatically; short answers left ungraded (or basic string matching)
    - Record LearnerQuizAttempt with score and raw data
    """
    quiz = get_object_or_404(Quiz.objects.prefetch_related("questions__options"), id=quiz_id)
    if request.method != "POST":
        return redirect("learn:quiz_detail", quiz_id=quiz.id)

    # Enforce enrollment if quiz attached to course
    course = None
    if quiz.lesson:
        course = quiz.lesson.module.course
    elif quiz.module:
        course = quiz.module.course

    if course:
        enrollment = Enrollment.objects.filter(learner=request.user, course=course).first()
        if not enrollment:
            messages.error(request, "You must be enrolled to submit this quiz.")
            return redirect("learn:course_detail", slug=course.slug)

    payload = request.POST.dict()
    # If answers come as JSON string in 'answers' key
    answers_raw = request.POST.get("answers")
    if answers_raw:
        try:
            answers = json.loads(answers_raw)
        except Exception:
            answers = {}
    else:
        # Expect keys like q_<question_id> => option_id or comma-separated for multi
        answers = {}
        for k, v in payload.items():
            if k.startswith("q_"):
                answers[k[2:]] = v

    total_points = Decimal("0.00")
    earned_points = Decimal("0.00")
    question_results = {}

    for question in quiz.questions.all():
        q_points = question.points or Decimal("1.00")
        total_points += q_points
        q_ans = answers.get(str(question.id))

        if question.question_type in ("mcq", "tf"):
            # single selection: q_ans is option id
            try:
                selected_opt = question.options.get(id=q_ans)
                if selected_opt.is_correct:
                    earned_points += q_points
                    question_results[str(question.id)] = {"correct": True, "selected": selected_opt.id}
                else:
                    question_results[str(question.id)] = {"correct": False, "selected": selected_opt.id}
            except Exception:
                question_results[str(question.id)] = {"correct": False, "selected": None}

        elif question.question_type == "multi":
            # expect comma-separated option ids or list
            selected = []
            if isinstance(q_ans, list):
                selected = q_ans
            elif isinstance(q_ans, str):
                selected = [s for s in q_ans.split(",") if s.strip()]
            # calculate fraction correct (simple approach: all correct and no incorrect)
            try:
                selected_opts = question.options.filter(id__in=selected)
                correct_opts = question.options.filter(is_correct=True)
                if selected_opts.count() == correct_opts.count() and set(o.id for o in selected_opts) == set(o.id for o in correct_opts):
                    earned_points += q_points
                    question_results[str(question.id)] = {"correct": True, "selected": selected}
                else:
                    question_results[str(question.id)] = {"correct": False, "selected": selected}
            except Exception:
                question_results[str(question.id)] = {"correct": False, "selected": selected}

        else:  # short answer -> save for manual grading
            question_results[str(question.id)] = {"correct": None, "response": q_ans}

    score = Decimal("0.00")
    if total_points > 0:
        score = (earned_points / total_points) * Decimal("100.00")

    attempt = LearnerQuizAttempt.objects.create(
        learner=request.user,
        quiz=quiz,
        started_at=timezone.now(),
        finished_at=timezone.now(),
        score=round(score, 2),
        data={"answers": answers, "question_results": question_results},
        graded=True if quiz.questions.exclude(question_type="short").count() == quiz.questions.count() else False,
    )

    messages.success(request, f"Quiz submitted — score: {attempt.score}%")
    return redirect("learn:quiz_result", attempt_id=attempt.id)


@login_required
def quiz_result_view(request, attempt_id):
    attempt = get_object_or_404(LearnerQuizAttempt, id=attempt_id, learner=request.user)
    return render(request, "learn/quizzes/quiz_result.html", {"attempt": attempt})

