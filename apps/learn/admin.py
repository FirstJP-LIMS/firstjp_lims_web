from django.contrib import admin
from .models import (
    CourseCategory,
    Course,
    Module,
    Lesson,
    MediaAsset,
    CourseDraft,
    DraftModule,
    DraftLesson,
)
from .services.course_promotion import promote_course_draft


# # --------------------
# # Core Admin Classes
# # --------------------

admin.site.register(CourseCategory)
admin.site.register(Course)
admin.site.register(Module)
admin.site.register(Lesson)
admin.site.register(MediaAsset)


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
#     # inlines = [ModuleInline]
#     ordering = ("title",)


# @admin.register(Module)
# class ModuleAdmin(admin.ModelAdmin):
#     list_display = ("title", "course", "position")
#     list_filter = ("course",)
#     search_fields = ("title",)
#     # inlines = [LessonInline]
#     ordering = ("course", "position")


# @admin.register(Lesson)
# class LessonAdmin(admin.ModelAdmin):
#     list_display = ("title", "module", "position", "is_previewable")
#     list_filter = ("module__course", "is_previewable")
#     search_fields = ("title", "content")
#     # inlines = [MediaAssetInline]
#     ordering = ("module", "position")


# @admin.register(MediaAsset)
# class MediaAssetAdmin(admin.ModelAdmin):
#     list_display = ("lesson", "media_type", "mime_type", "file_size")
#     list_filter = ("media_type",)
#     search_fields = ("lesson__title",)
#     ordering = ("lesson",)

# Facilitators 
@admin.register(CourseDraft)
class CourseDraftAdmin(admin.ModelAdmin):
    list_display = ('title', 'created_by', 'status', 'created_at',)
    list_filter = ('status', 'category')
    search_fields = ('title', 'short_description')
    readonly_fields = ('created_by', 'status', 'created_at', 'updated_at',)
    actions = ['approve_drafts', 'reject_drafts']

    fieldsets = (
        ("Draft Metadata", {
            "fields": ('title', 'slug', 'created_by', 'status',)}),
        ("Course Content", {
            "fields": (
                'short_description',
                'long_description',
                'category',
                'tags',
                'difficulty',
                'thumbnail',
            )
        }),
        ("Review", {
            "fields": ('review_notes',),
        }),
        ("Timestamps", {
            "fields": ('created_at', 'updated_at'),
        }),
    )

    def has_add_permission(self, request):
        return False  # Admins cannot create drafts

    def has_delete_permission(self, request, obj=None):
        return False  # Preserve audit trail

    @admin.action(description="Approve selected drafts (Publish)")
    def approve_drafts(self, request, queryset):
        approved = 0

        for draft in queryset.filter(status='submitted'):
            promote_course_draft(draft)
            approved += 1

        self.message_user(
            request,
            f"{approved} course draft(s) approved and published."
        )

    @admin.action(description="Reject selected drafts")
    def reject_drafts(self, request, queryset):
        updated = queryset.update(status='rejected')
        self.message_user(
            request,
            f"{updated} course draft(s) rejected."
        )


class DraftLessonInline(admin.TabularInline):
    model = DraftLesson
    extra = 0
    readonly_fields = [f.name for f in DraftLesson._meta.fields]

    def has_add_permission(self, request, obj=None):
        return False


class DraftModuleInline(admin.TabularInline):
    model = DraftModule
    extra = 0
    readonly_fields = [f.name for f in DraftModule._meta.fields]
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False



"""
@login_required
@user_passes_test(lambda u: u.is_staff)
def admin_draft_review_detail_view(request, pk):
    draft = get_object_or_404(CourseDraft, pk=pk)
    return render(request, 'lms/admin/draft_review_detail.html', {
        'draft': draft
    })

@login_required
@user_passes_test(lambda u: u.is_staff)
def admin_draft_review_list_view(request):
    drafts = CourseDraft.objects.filter(status='submitted')
    return render(request, 'lms/admin/draft_review_list.html', {
        'drafts': drafts
    })

    
@login_required
@user_passes_test(lambda u: u.is_staff)
def admin_draft_approve_view(request, pk):
    draft = get_object_or_404(CourseDraft, pk=pk, status='submitted')

    promote_course_draft(draft)

    return redirect('lms:admin_draft_review_list')

@login_required
@user_passes_test(lambda u: u.is_staff)
def admin_draft_reject_view(request, pk):
    draft = get_object_or_404(CourseDraft, pk=pk)

    if request.method == 'POST':
        notes = request.POST.get('review_notes', '')
        draft.status = 'rejected'
        draft.review_notes = notes
        draft.save(update_fields=['status', 'review_notes'])
        return redirect('lms:admin_draft_review_list')

    return render(request, 'lms/admin/draft_reject_confirm.html', {
        'draft': draft
    })

    
"""

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
