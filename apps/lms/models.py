# apps/learn/models.py
import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.contrib.auth import get_user_model

User = get_user_model()


# ---------- Utilities / Abstracts ----------

class TimeStampedModel(models.Model):
    """Abstract model that provides created/updated timestamps."""
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


# ---------- Profiles ----------

class LearnerProfile(TimeStampedModel):
    """Extended profile for learners."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='learner_profile')
    bio = models.TextField(blank=True)
    organization = models.CharField(max_length=255, blank=True, null=True)
    job_title = models.CharField(max_length=255, blank=True, null=True)
    country = models.CharField(max_length=100, blank=True, null=True)
    # optional public facing fields
    public_display_name = models.CharField(max_length=255, blank=True, null=True)
    avatar = models.ImageField(upload_to='learn/avatars/', null=True, blank=True)

    def __str__(self):
        return f"LearnerProfile({self.user.email})"


class FacilitatorProfile(TimeStampedModel):
    """Extended profile for facilitators/instructors."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='facilitator_profile')
    bio = models.TextField(blank=True)
    credentials = models.CharField(max_length=512, blank=True, null=True,
                                   help_text="Qualifications, degrees, licenses")
    organization = models.CharField(max_length=255, blank=True, null=True)
    verified = models.BooleanField(default=False, help_text="Platform has verified this facilitator")
    avatar = models.ImageField(upload_to='learn/facilitators/', null=True, blank=True)
    linkedin_url = models.URLField(blank=True, null=True)

    def __str__(self):
        return f"FacilitatorProfile({self.user.email})"


# ---------- Taxonomy ----------

class CourseCategory(TimeStampedModel):
    """High-level category for grouping courses (Hematology, Microbiology, etc.)."""
    slug = models.SlugField(max_length=120, unique=True)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["title"]

    def __str__(self):
        return self.title


class CourseTag(TimeStampedModel):
    """Lightweight tag for discoverability."""
    name = models.CharField(max_length=64, unique=True)

    def __str__(self):
        return self.name


# ---------- Media & Content ----------

class MediaAsset(TimeStampedModel):
    """
    Generic media asset used by lessons.
    Stores file references (video/pdf/image) and metadata.
    """
    MEDIA_TYPE_CHOICES = [
        ('video', 'Video'),
        ('document', 'Document'),
        ('image', 'Image'),
        ('slide', 'Slide Deck'),
        ('other', 'Other'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    media_type = models.CharField(max_length=32, choices=MEDIA_TYPE_CHOICES)
    file = models.FileField(upload_to='learn/media/', blank=True, null=True)
    external_url = models.URLField(blank=True, null=True, help_text="CDN or external hosted URL")
    duration_seconds = models.PositiveIntegerField(blank=True, null=True, help_text="For videos")
    size_bytes = models.BigIntegerField(blank=True, null=True)
    thumbnail = models.ImageField(upload_to='learn/media_thumbs/', blank=True, null=True)

    class Meta:
        indexes = [
            models.Index(fields=["media_type"]),
        ]

    def __str__(self):
        return f"{self.title} ({self.media_type})"


# ---------- Course Model Hierarchy ----------

class Course(TimeStampedModel):
    """
    Course is the main container. Use UUID if you prefer; using integer PK for simplicity.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=300)
    slug = models.SlugField(max_length=300, unique=True)
    short_description = models.CharField(max_length=512, blank=True)
    long_description = models.TextField(blank=True)
    category = models.ForeignKey(CourseCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name='courses')
    tags = models.ManyToManyField(CourseTag, blank=True, related_name='courses')
    thumbnail = models.ImageField(upload_to='learn/course_thumbs/', blank=True, null=True)
    difficulty = models.CharField(max_length=50, blank=True, null=True, help_text="Beginner/Intermediate/Advanced")
    published = models.BooleanField(default=False, db_index=True)
    published_at = models.DateTimeField(blank=True, null=True)
    featured = models.BooleanField(default=False, db_index=True)
    # multiple facilitators possible
    facilitators = models.ManyToManyField(User, related_name='courses_authored', blank=True)

    # discoverability (text search)
    search_vector = SearchVectorField(null=True, blank=True)

    class Meta:
        ordering = ["-featured", "-published_at", "title"]
        indexes = [
            models.Index(fields=["published", "featured"]),
            GinIndex(fields=["search_vector"]),
        ]

    def __str__(self):
        return self.title

    def publish(self):
        if not self.published:
            self.published = True
            self.published_at = timezone.now()
            self.save(update_fields=["published", "published_at"])


class Module(TimeStampedModel):
    """Module groups lessons within a course. Ordered by `position`."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='modules')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    position = models.PositiveIntegerField(default=0, help_text="Ordering index")

    class Meta:
        ordering = ["position"]
        unique_together = (("course", "position"),)

    def __str__(self):
        return f"{self.course.title} — {self.title}"


class Lesson(TimeStampedModel):
    """Atomic learning unit. Can reference one or more MediaAssets."""
    LESSON_TYPE_CHOICES = [
        ('video', 'Video'),
        ('article', 'Article'),
        ('document', 'Document'),
        ('quiz', 'Quiz'),
        ('interactive', 'Interactive'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name='lessons')
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=320, blank=True, null=True)
    lesson_type = models.CharField(max_length=32, choices=LESSON_TYPE_CHOICES, default='video')
    summary = models.TextField(blank=True)
    body = models.TextField(blank=True, help_text="Optional HTML/markdown stored as text")
    position = models.PositiveIntegerField(default=0)
    duration_seconds = models.PositiveIntegerField(blank=True, null=True)
    required = models.BooleanField(default=True)

    media = models.ManyToManyField(MediaAsset, blank=True, related_name='lessons')

    class Meta:
        ordering = ["position"]
        unique_together = (("module", "position"),)

    def __str__(self):
        return f"{self.module.course.title} — {self.title}"


# ---------- Assessments ----------

class Quiz(TimeStampedModel):
    """Quiz can be attached to a lesson or a module (module-level quiz)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    instructions = models.TextField(blank=True)
    time_limit_seconds = models.PositiveIntegerField(blank=True, null=True)
    max_attempts = models.PositiveIntegerField(default=3)
    randomize_questions = models.BooleanField(default=False)
    # relation: optional one-to-one to a lesson (quiz embedded in a lesson)
    lesson = models.OneToOneField(Lesson, on_delete=models.CASCADE, null=True, blank=True, related_name='quiz')

    def __str__(self):
        return self.title


class Question(TimeStampedModel):
    """A question for quizzes."""
    QUESTION_TYPE = [
        ('mcq', 'Multiple Choice'),
        ('multi', 'Multiple Selection'),
        ('tf', 'True / False'),
        ('short', 'Short Answer'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='questions')
    prompt = models.TextField()
    question_type = models.CharField(max_length=16, choices=QUESTION_TYPE)
    points = models.DecimalField(max_digits=6, decimal_places=2, default=1.0)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["position"]

    def __str__(self):
        return f"Q: {self.prompt[:60]}"


class Option(models.Model):
    """Option for MCQ/Multi questions."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='options')
    text = models.CharField(max_length=1000)
    is_correct = models.BooleanField(default=False)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["position"]

    def __str__(self):
        return f"Option({self.text[:60]})"


class LearnerQuizAttempt(TimeStampedModel):
    """Records a learner's attempt at a quiz."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    learner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='quiz_attempts')
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='attempts')
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)
    score = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    data = models.JSONField(default=dict, blank=True, help_text="Store question responses / raw payload")
    graded = models.BooleanField(default=False)

    class Meta:
        unique_together = (("learner", "quiz", "started_at"),)

    def __str__(self):
        return f"Attempt({self.learner_id}, {self.quiz_id})"


# ---------- Enrollment & Progress ----------

class Enrollment(TimeStampedModel):
    """Represents a learner enrolled in a course."""
    ENROLLMENT_STATUS = [
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('dropped', 'Dropped'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    learner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='enrollments')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='enrollments')
    enrolled_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=24, choices=ENROLLMENT_STATUS, default='active')
    progress_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0.0)
    # In case of monetization:
    paid = models.BooleanField(default=False)

    class Meta:
        unique_together = (("learner", "course"),)
        indexes = [
            models.Index(fields=["learner", "course"]),
        ]

    def __str__(self):
        return f"Enrollment({self.learner.email}, {self.course.title})"


class LearnerProgress(TimeStampedModel):
    """
    Tracks granular lesson completion for a given enrollment.
    One row per (enrollment, lesson).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name='progress_items')
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name='progress_records')
    completed = models.BooleanField(default=False)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    time_spent_seconds = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = (("enrollment", "lesson"),)
        indexes = [
            models.Index(fields=["enrollment", "lesson"]),
        ]

    def __str__(self):
        return f"Progress({self.enrollment_id}, {self.lesson.title})"


class Certificate(TimeStampedModel):
    """Issued certificate for completed course."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    enrollment = models.OneToOneField(Enrollment, on_delete=models.CASCADE, related_name='certificate')
    issued_at = models.DateTimeField(auto_now_add=True)
    certificate_name = models.CharField(max_length=255)
    certificate_id = models.CharField(max_length=128, unique=True, db_index=True)
    pdf = models.FileField(upload_to='learn/certificates/', blank=True, null=True)
    meta = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"Certificate({self.certificate_id})"


# ---------- Engagement / Community ----------

class DiscussionThread(TimeStampedModel):
    """
    Course or lesson discussion thread.
    If `lesson` is null then it's course-level.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='threads')
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name='threads', null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='threads_created')
    title = models.CharField(max_length=400)
    body = models.TextField()
    pinned = models.BooleanField(default=False)
    closed = models.BooleanField(default=False)

    class Meta:
        ordering = ["-pinned", "-created_at"]

    def __str__(self):
        return f"Thread({self.title[:60]})"


class DiscussionReply(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    thread = models.ForeignKey(DiscussionThread, on_delete=models.CASCADE, related_name='replies')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='replies_created')
    body = models.TextField()

    def __str__(self):
        return f"Reply({self.thread_id})"


class Announcement(TimeStampedModel):
    """Announcements from facilitators about courses."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='announcements')
    title = models.CharField(max_length=255)
    body = models.TextField()
    visible_from = models.DateTimeField(default=timezone.now)
    visible_until = models.DateTimeField(null=True, blank=True)
    pinned = models.BooleanField(default=False)

    class Meta:
        ordering = ["-pinned", "-visible_from"]

    def __str__(self):
        return self.title


# ---------- Platform-level Content ----------

class LandingBanner(TimeStampedModel):
    """Configurable content blocks for the landing page."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    subtitle = models.CharField(max_length=512, blank=True)
    image = models.ImageField(upload_to='learn/banners/', blank=True, null=True)
    cta_text = models.CharField(max_length=120, blank=True)
    cta_url = models.CharField(max_length=512, blank=True)  # internal or external

    def __str__(self):
        return f"Banner({self.title})"


class CourseFeedback(TimeStampedModel):
    """Learner feedback and ratings for courses."""
    RATING_CHOICES = [(i, i) for i in range(1, 6)]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='feedback')
    learner = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='feedback_given')
    rating = models.IntegerField(choices=RATING_CHOICES, default=5)
    comment = models.TextField(blank=True)
    moderated = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Feedback({self.course.title}, {self.rating})"


class NewsletterSubscriber(TimeStampedModel):
    email = models.EmailField(unique=True)
    name = models.CharField(max_length=255, blank=True, null=True)
    confirmed = models.BooleanField(default=False)

    def __str__(self):
        return self.email





# from django.db import models
# from django.conf import settings # Use settings.AUTH_USER_MODEL for User FK
# from apps.core.managers import TenantAwareManager # Keep TenantAwareManager if needed for related models
# from apps.tenants.models import Vendor # Only if tracking a vendor's *use* of a course, not the course itself

# # ------------------------------------------------
# # Facilitator Model (Links User to Instructor Role)
# # ------------------------------------------------
# class Facilitator(models.Model):
#     """
#     Represents a platform user who has been designated as an instructor.
#     This links the global course content to an internal staff member.
#     """
#     user = models.OneToOneField(
#         settings.AUTH_USER_MODEL,
#         on_delete=models.CASCADE,
#         related_name='facilitator_profile'
#     )
#     bio = models.TextField(blank=True, verbose_name="Instructor Biography")
#     is_active = models.BooleanField(default=True)
    
#     # Note: No 'vendor' field here, as the content they teach is platform-global.
    
#     def __str__(self):
#         return self.user.get_full_name() or self.user.email

# # ------------------------------------------------
# # Course Model (Platform-Global)
# # ------------------------------------------------
# class Course(models.Model):
#     """Platform-owned courses available to all tenants/users."""
#     title = models.CharField(max_length=255)
#     slug = models.SlugField(max_length=255, unique=True)
#     description = models.TextField()
#     facilitator = models.ForeignKey(Facilitator, on_delete=models.SET_NULL, null=True, related_name='courses')
#     is_published = models.BooleanField(default=False)
#     created_at = models.DateTimeField(auto_now_add=True)

#     class Meta:
#         ordering = ['title']

#     def __str__(self):
#         return self.title

# # ------------------------------------------------
# # Lesson Model (Platform-Global)
# # ------------------------------------------------
# class Lesson(models.Model):
#     """Individual modules or topics within a Course."""
#     course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='lessons')
#     title = models.CharField(max_length=255)
#     content = models.TextField(help_text="HTML or rich text content of the lesson.")
#     video_url = models.URLField(blank=True, null=True)
#     order = models.PositiveSmallIntegerField(default=0) # For lesson sequence
    
#     class Meta:
#         ordering = ['order']
#         unique_together = ('course', 'order')

#     def __str__(self):
#         return f"{self.course.title}: {self.title}"

# # ------------------------------------------------
# # Enrollment Model (Tenant-Aware Usage Tracking)
# # ------------------------------------------------
# # This model tracks a tenant's user taking a global course.
# class Enrollment(models.Model):
#     """Tracks which user (and implicitly, which tenant) is enrolled in which course."""
#     user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='enrollments')
#     course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='enrollments')
#     enrolled_on = models.DateTimeField(auto_now_add=True)
#     completed_lessons = models.ManyToManyField(Lesson, blank=True)
    
#     # We can use the TenantAwareManager here to scope enrollments if needed, 
#     # but since the User model already scopes to a Vendor, it's often redundant.
#     # objects = TenantAwareManager() 
    
#     class Meta:
#         unique_together = ('user', 'course')
#         # We can enforce that the user must belong to a vendor to enroll 
#         # (based on your User model design)
        
#     def __str__(self):
#         return f"{self.user.email} enrolled in {self.course.title}"
    
