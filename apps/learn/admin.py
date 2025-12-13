# from django.contrib import admin
# from django.utils.html import format_html
# from django import forms

# from .models import (
#     CourseCategory,
#     Course,
#     Module,
#     Lesson,
#     MediaAsset,
#     Quiz,
#     Question,
#     Option,
#     Enrollment,
#     # LessonProgress,
#     # UserLessonInteraction,
#     Certificate,
#     # Feedback,
#     Announcement,
#     DiscussionThread,
#     DiscussionReply,
#     LearningPath,
#     LearningPathCourse,
#     LearningPathProgress,
#     Cohort,
#     CohortMembership,
#     Assignment,
#     # AssignmentSubmission,
# )


# # --------------------
# # Inline Admin Classes
# # --------------------

# class MediaAssetInline(admin.TabularInline):
#     model = MediaAsset
#     extra = 1


# class LessonInline(admin.TabularInline):
#     model = Lesson
#     extra = 1
#     fields = ("title", "position", "slug", "is_previewable")
#     ordering = ("position",)


# class ModuleInline(admin.TabularInline):
#     model = Module
#     extra = 1
#     fields = ("title", "position", "slug")
#     ordering = ("position",)


# class OptionInline(admin.TabularInline):
#     model = Option
#     extra = 1
#     fields = ("text", "is_correct", "feedback")


# class QuestionInline(admin.TabularInline):
#     model = Question
#     extra = 1
#     fields = ("text", "question_type", "explanation")


# # --------------------
# # Core Admin Classes
# # --------------------

# @admin.register(CourseCategory)
# class CategoryAdmin(admin.ModelAdmin):
#     list_display = ("name", "slug")
#     search_fields = ("name",)


# @admin.register(Course)
# class CourseAdmin(admin.ModelAdmin):
#     list_display = (
#         "title", "slug", "author", "difficulty_level",
#         "is_published", "created_at"
#     )
#     list_filter = ("is_published", "difficulty_level", "created_at")
#     search_fields = ("title", "description", "tags")
#     prepopulated_fields = {"slug": ("title",)}
#     inlines = [ModuleInline]
#     ordering = ("title",)


# @admin.register(Module)
# class ModuleAdmin(admin.ModelAdmin):
#     list_display = ("title", "course", "position")
#     list_filter = ("course",)
#     search_fields = ("title",)
#     inlines = [LessonInline]
#     ordering = ("course", "position")


# @admin.register(Lesson)
# class LessonAdmin(admin.ModelAdmin):
#     list_display = ("title", "module", "position", "is_previewable")
#     list_filter = ("module__course", "is_previewable")
#     search_fields = ("title", "content")
#     inlines = [MediaAssetInline]
#     ordering = ("module", "position")


# @admin.register(MediaAsset)
# class MediaAssetAdmin(admin.ModelAdmin):
#     list_display = ("lesson", "media_type", "mime_type", "file_size")
#     list_filter = ("media_type",)
#     search_fields = ("lesson__title",)
#     ordering = ("lesson",)


# # --------------------
# # Assessment Admin
# # --------------------

# @admin.register(Quiz)
# class QuizAdmin(admin.ModelAdmin):
#     list_display = ("id", "lesson", "module", "time_limit", "passing_score")
#     list_filter = ("time_limit",)
#     search_fields = ("lesson__title", "module__title")
#     inlines = [QuestionInline]


# @admin.register(Question)
# class QuestionAdmin(admin.ModelAdmin):
#     list_display = ("text", "quiz", "question_type")
#     list_filter = ("question_type",)
#     search_fields = ("text",)
#     inlines = [OptionInline]


# @admin.register(Option)
# class OptionAdmin(admin.ModelAdmin):
#     list_display = ("question", "text", "is_correct")
#     list_filter = ("is_correct",)
#     search_fields = ("text",)


# @admin.register(Assignment)
# class AssignmentAdmin(admin.ModelAdmin):
#     list_display = ("title", "course", "release_date", "due_date", "is_active")
#     list_filter = ("is_active", "release_date", "course")
#     search_fields = ("title", "description")


# # @admin.register(AssignmentSubmission)
# # class AssignmentSubmissionAdmin(admin.ModelAdmin):
# #     list_display = ("assignment", "student", "submitted_at", "grade", "status")
# #     list_filter = ("status",)
# #     search_fields = ("student__email", "assignment__title")


# # --------------------
# # Enrollment & Progress
# # --------------------

# @admin.register(Enrollment)
# class EnrollmentAdmin(admin.ModelAdmin):
#     list_display = ("user", "course", "enrollment_date", "progress_percent", "is_active")
#     list_filter = ("is_active", "enrollment_date")
#     search_fields = ("user__email", "course__title")
#     ordering = ("-enrollment_date",)


# # @admin.register(LessonProgress)
# # class LessonProgressAdmin(admin.ModelAdmin):
# #     list_display = ("enrollment", "lesson", "is_completed", "progress_percent")
# #     list_filter = ("is_completed",)
# #     search_fields = ("enrollment__user__email", "lesson__title")


# # @admin.register(UserLessonInteraction)
# # class UserLessonInteractionAdmin(admin.ModelAdmin):
# #     list_display = ("user", "lesson", "action_type", "timestamp")
# #     list_filter = ("action_type",)
# #     search_fields = ("user__email", "lesson__title")


# # --------------------
# # Community Admin
# # --------------------

# @admin.register(Announcement)
# class AnnouncementAdmin(admin.ModelAdmin):
#     list_display = ("course", "title", "created_at")
#     list_filter = ("course",)
#     search_fields = ("title", "content")


# @admin.register(DiscussionThread)
# class DiscussionThreadAdmin(admin.ModelAdmin):
#     list_display = ("course", "user", "title", "created_at")
#     search_fields = ("title", "content", "user__email")
#     list_filter = ("course",)


# @admin.register(DiscussionReply)
# class DiscussionReplyAdmin(admin.ModelAdmin):
#     list_display = ("thread", "user", "parent", "created_at", "is_deleted")
#     list_filter = ("is_deleted",)
#     search_fields = ("content", "user__email")


# # --------------------
# # Certificates & Feedback
# # --------------------

# @admin.register(Certificate)
# class CertificateAdmin(admin.ModelAdmin):
#     list_display = ("user", "course", "issued_at", "is_active")
#     search_fields = ("user__email", "course__title")


# # @admin.register(Feedback)
# # class FeedbackAdmin(admin.ModelAdmin):
# #     list_display = ("user", "course", "rating", "created_at")
# #     list_filter = ("rating",)
# #     search_fields = ("user__email", "comment")


# # --------------------
# # Learning Path Admin
# # --------------------

# class LearningPathCourseInline(admin.TabularInline):
#     model = LearningPathCourse
#     extra = 1


# @admin.register(LearningPath)
# class LearningPathAdmin(admin.ModelAdmin):
#     list_display = ("title", "description", "created_at")
#     search_fields = ("title", "description")
#     inlines = [LearningPathCourseInline]


# @admin.register(LearningPathProgress)
# class LearningPathProgressAdmin(admin.ModelAdmin):
#     list_display = ("user", "learning_path", "progress_percent", "updated_at")
#     search_fields = ("user__email", "learning_path__title")


# # --------------------
# # Cohort Admin
# # --------------------

# class CohortMembershipInline(admin.TabularInline):
#     model = CohortMembership
#     extra = 1


# @admin.register(Cohort)
# class CohortAdmin(admin.ModelAdmin):
#     list_display = ("name", "course", "start_date", "end_date", "instructor")
#     list_filter = ("course",)
#     search_fields = ("name", "course__title")
#     inlines = [CohortMembershipInline]


# @admin.register(CohortMembership)
# class CohortMembershipAdmin(admin.ModelAdmin):
#     list_display = ("cohort", "student", "joined_at")
#     search_fields = ("student__email", "cohort__name")
