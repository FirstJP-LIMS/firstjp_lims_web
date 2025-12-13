from django import forms
from .models import (
    Course,
    Module,
    Lesson,
    Quiz,
    Question,
    Option,
    Assignment,
    AssignmentSubmission,
    LearningPath,
    Cohort,
)


class CourseForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = ["title", "slug", "description", "difficulty_level",
                  "language", "is_published", "tags", "category"]


class ModuleForm(forms.ModelForm):
    class Meta:
        model = Module
        fields = ["course", "title", "slug", "position"]


class LessonForm(forms.ModelForm):
    class Meta:
        model = Lesson
        fields = [
            "module", "title", "slug", "content", "position",
            "is_previewable", "estimated_duration"
        ]


class QuizForm(forms.ModelForm):
    class Meta:
        model = Quiz
        fields = ["lesson", "module", "time_limit", "passing_score"]


class QuestionForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = ["quiz", "text", "question_type", "explanation"]


class OptionForm(forms.ModelForm):
    class Meta:
        model = Option
        fields = ["question", "text", "is_correct", "feedback"]


class AssignmentForm(forms.ModelForm):
    class Meta:
        model = Assignment
        fields = ["course", "title", "description",
                  "release_date", "due_date", "is_active", "allow_late_submission"]


class AssignmentSubmissionForm(forms.ModelForm):
    class Meta:
        model = AssignmentSubmission
        fields = ["assignment", "content", "attachment"]


class LearningPathForm(forms.ModelForm):
    class Meta:
        model = LearningPath
        fields = ["title", "description"]


class CohortForm(forms.ModelForm):
    class Meta:
        model = Cohort
        fields = ["course", "name", "start_date", "end_date", "instructor"]
