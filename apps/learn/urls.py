from django.urls import path

from .views.courses import course_list_view, course_detail_view, enroll_in_course_view, continue_course_view
from .views.modules import module_detail_view
from .views.lessons import lesson_detail_view, mark_lesson_complete_view
from .views.quizzes import quiz_view, quiz_submit_view, quiz_result_view
from .views.assignments import assignment_detail_view, assignment_submit_view, grade_submission_view
from .views.discussions import thread_list_view, thread_create_view, reply_create_view
from .views.learning_paths import learning_path_list_view, learning_path_detail_view, learning_path_enroll_view
from .views.cohorts import cohort_detail_view, cohort_join_view
from .views.certificates import certificate_view, generate_certificate_view
from .views import landing

app_name = "learn"

urlpatterns = [
    # generic pages 
    path("", landing.index_page, name="index"),

    # courses
    path("courses", course_list_view, name="course_list"),
    path("course/<slug:slug>/", course_detail_view, name="course_detail"),
    path("course/<slug:course_slug>/enroll/", enroll_in_course_view, name="enroll"),
    path("course/<slug:course_slug>/continue/", continue_course_view, name="continue_course"),

    # modules & lessons
    path("module/<uuid:module_id>/", module_detail_view, name="module_detail"),
    path("lesson/<uuid:lesson_id>/", lesson_detail_view, name="lesson_detail"),
    path("lesson/<uuid:lesson_id>/complete/", mark_lesson_complete_view, name="lesson_mark_complete"),

    # # quizzes
    path("quiz/<uuid:quiz_id>/", quiz_view, name="quiz_detail"),
    path("quiz/<uuid:quiz_id>/submit/", quiz_submit_view, name="quiz_submit"),
    path("quiz/result/<uuid:attempt_id>/", quiz_result_view, name="quiz_result"),

    # assignments
    path("assignment/<uuid:assignment_id>/", assignment_detail_view, name="assignment_detail"),
    path("assignment/<uuid:assignment_id>/submit/", assignment_submit_view, name="assignment_submit"),
    path("submission/<uuid:submission_id>/grade/", grade_submission_view, name="grade_submission"),

    # discussions
    path("course/<slug:course_slug>/threads/", thread_list_view, name="thread_list"),
    path("course/<slug:course_slug>/threads/new/", thread_create_view, name="thread_create"),
    path("thread/<uuid:thread_id>/reply/", reply_create_view, name="reply_create"),

    # learning paths
    path("paths/", learning_path_list_view, name="learning_path_list"),
    path("path/<slug:slug>/", learning_path_detail_view, name="learning_path_detail"),
    path("path/<slug:slug>/enroll/", learning_path_enroll_view, name="learning_path_enroll"),

    # cohorts
    path("cohort/<uuid:cohort_id>/", cohort_detail_view, name="cohort_detail"),
    path("cohort/<uuid:cohort_id>/join/", cohort_join_view, name="cohort_join"),

    # certificates
    path("certificate/<uuid:enrollment_id>/", certificate_view, name="certificate_detail"),
    path("certificate/<uuid:enrollment_id>/generate/", generate_certificate_view, name="certificate_generate"),
]
