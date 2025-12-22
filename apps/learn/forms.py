# Facilitator
# apps/learn/forms.py
from django import forms
from .models import (
    CourseDraft,
    DraftModule,
    DraftLesson,
    MediaAsset
)

class CourseDraftForm(forms.ModelForm):
    class Meta:
        model = CourseDraft
        fields = ['title', 'short_description', 'long_description', 'category', 'tags', 'thumbnail', 'difficulty', 'review_notes',]

        widgets = {
            'tags': forms.CheckboxSelectMultiple,
        }


class DraftModuleForm(forms.ModelForm):
    class Meta:
        model = DraftModule
        fields = ['title', 'description', 'position']


class DraftLessonForm(forms.ModelForm):
    class Meta:
        model = DraftLesson
        fields = [
            'title',
            'lesson_type',
            'summary',
            'body',
            'position',
            'duration_seconds',
            'media',
        ]
        widgets = {
            'media': forms.CheckboxSelectMultiple,
        }

class MediaAssetForm(forms.ModelForm):
    class Meta:
        model = MediaAsset
        fields = [
            'title',
            'media_type',
            'file',
            'external_url',
            'duration_seconds',
            'thumbnail',
        ]



# from django import forms
# from .models import (
#     Course,
#     Module,
#     Lesson,
#     Quiz,
#     Question,
#     Option,
#     Assignment,
#     # AssignmentSubmission,
#     LearningPath,
#     Cohort,
# )


# class CourseForm(forms.ModelForm):
#     class Meta:
#         model = Course
#         fields = ["title", "slug", "short_description", "difficulty",
#                   "published", "tags", "category"]


# class ModuleForm(forms.ModelForm):
#     class Meta:
#         model = Module
#         fields = ["course", "title", "slug", "position"]


# class LessonForm(forms.ModelForm):
#     class Meta:
#         model = Lesson
#         fields = [
#             "module", "title", "slug", "content", "position",
#             "is_previewable", "estimated_duration"
#         ]


# class QuizForm(forms.ModelForm):
#     class Meta:
#         model = Quiz
#         fields = ["lesson", "module", "time_limit", "passing_score"]


# class QuestionForm(forms.ModelForm):
#     class Meta:
#         model = Question
#         fields = ["quiz", "text", "question_type", "explanation"]


# class OptionForm(forms.ModelForm):
#     class Meta:
#         model = Option
#         fields = ["question", "text", "is_correct", "feedback"]


# class AssignmentForm(forms.ModelForm):
#     class Meta:
#         model = Assignment
#         fields = ["course", "title", "description",
#                   "release_date", "due_date", "is_active", "allow_late_submission"]


# class AssignmentSubmissionForm(forms.ModelForm):
#     class Meta:
#         model = AssignmentSubmission
#         fields = ["assignment", "content", "attachment"]


# class LearningPathForm(forms.ModelForm):
#     class Meta:
#         model = LearningPath
#         fields = ["title", "description"]


# class CohortForm(forms.ModelForm):
#     class Meta:
#         model = Cohort
#         fields = ["course", "name", "start_date", "end_date", "instructor"]

