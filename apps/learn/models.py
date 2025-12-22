"""
Facilitator
    → CourseDraft (CRUD)
    → DraftModule (CRUD)
    → DraftLesson (CRUD)
    → MediaAsset (Upload)
    → Submit Draft
            ↓
    Admin
    → Review
    → Approve
    → promote_course_draft()
            ↓
    Public Course
"""

# apps/learn/models.py
import uuid
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.db.models import Q, UniqueConstraint
from django.utils import timezone

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
    """Set by Admin: High-level category for grouping courses (Hematology, Microbiology, etc.)."""
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["title"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        # Only generate slug if not set
        if not self.slug:
            base_slug = slugify(self.title)
            slug = base_slug
            counter = 1
            # Ensure uniqueness
            while CourseCategory.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)


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
    mime_type = models.CharField(max_length=128, blank=True, null=True, help_text="MIME type for rendering")
    thumbnail = models.ImageField(upload_to='learn/media_thumbs/', blank=True, null=True)

    class Meta:
        indexes = [
            models.Index(fields=["media_type"]),
        ]

    def __str__(self):
        return f"{self.title} ({self.media_type})"


from django.utils.text import slugify
from django.db.models import Q 

# ---------- Course Model Hierarchy ----------

class Course(TimeStampedModel):
     
    DIFFICULTY_STATUS = [
        ('basic', 'Basic'),
        ('intermediate', 'Intermediate'),
        ('advanced', 'Advanced'),
    ]
    """
    Course is the main container. UUID PK for global uniqueness.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=300)
    # Note: slug is not null/blank since it will be auto-generated
    slug = models.SlugField(max_length=300, unique=True, blank=True) # Added blank=True
    short_description = models.CharField(max_length=512, blank=True)
    long_description = models.TextField(blank=True)
    category = models.ForeignKey(CourseCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name='courses')
    tags = models.ManyToManyField(CourseTag, blank=True, related_name='courses')
    thumbnail = models.ImageField(upload_to='learn/course_thumbs/', blank=True, null=True)
    
    difficulty = models.CharField(max_length=50, choices=DIFFICULTY_STATUS, blank=True, null=True)

    published = models.BooleanField(default=False, db_index=True)
    published_at = models.DateTimeField(blank=True, null=True)
    featured = models.BooleanField(default=False, db_index=True)
    # multiple facilitators possible
    facilitators = models.ManyToManyField(User, related_name='courses_authored', blank=True)

    # discoverability (text search)
    search_vector = SearchVectorField(null=True, blank=True)

    # denormalized counts (helpful for performance; keep updated in app logic or celery tasks)
    lessons_count = models.PositiveIntegerField(default=0)
    modules_count = models.PositiveIntegerField(default=0)


    base_price = models.DecimalField(max_digits=8, decimal_places=2,
        default=0.00,
        help_text="Base price of the course in USD. Set to 0.00 for free courses."
    )

    is_free = models.BooleanField(
        default=False,
        editable=False,
        help_text="Automatically set to True if base_price is 0.00"
    )


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
    
    def save(self, *args, **kwargs):
        # Set course to free 
        self.is_free = self.base_price == 0.00
        
        # use the catogory and title
        # 1. Generate the base slug only if it's a new object or the title changed
        if not self.pk or self.title != self.__original_title:
            category_slug_part = ""
            if self.category and self.category.slug:
                category_slug_part = f"{self.category.slug}-"
            
            # Combine category and title
            base_slug = slugify(f"{category_slug_part}{self.title}")
            
            # Ensure slug is unique, appending a counter if necessary
            unique_slug = base_slug
            num = 1
            while Course.objects.filter(slug=unique_slug).exclude(pk=self.pk).exists():
                unique_slug = f'{base_slug}-{num}'
                num += 1
            
            self.slug = unique_slug
        super().save(*args, **kwargs)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Store original title to detect changes in save method
        self.__original_title = self.title


class Module(TimeStampedModel):
    """Module groups lessons within a course. Ordered by `position`."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='modules')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    position = models.PositiveIntegerField(default=0, help_text="Ordering index")
    
    # 🌟 NEW FIELD: Slug for use in URLs 🌟
    slug = models.SlugField(max_length=255, blank=True)

    class Meta:
        ordering = ["position"]
        constraints = [
            UniqueConstraint(fields=['course', 'position'], name='unique_module_position_per_course'),
            # 🌟 NEW CONSTRAINT: Slug must be unique per course 🌟
            UniqueConstraint(fields=['course', 'slug'], name='unique_module_slug_per_course')
        ]
        indexes = [
            models.Index(fields=["course", "position"]),
        ]

    def __str__(self):
        return f"{self.course.title} — {self.title}"

    # 🌟 NEW SLUG GENERATION METHOD 🌟
    def save(self, *args, **kwargs):
        # Store original title to detect changes for slug regeneration
        original_title = getattr(self, '__original_title', None)
        
        # Only generate/update slug if it's a new record OR the title has changed
        if not self.pk or self.title != original_title:
            
            # 1. Generate the base slug from the title
            base_slug = slugify(self.title)
            
            # 2. Ensure the slug is unique within its parent course
            unique_slug = base_slug
            num = 1
            
            # Query the database for existing slugs under the same course, excluding self
            while Module.objects.filter(course=self.course, slug=unique_slug).exclude(pk=self.pk).exists():
                unique_slug = f'{base_slug}-{num}'
                num += 1
            
            self.slug = unique_slug
        
        self.__original_title = self.title
        super().save(*args, **kwargs)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__original_title = self.title


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
    
    # 🌟 MODIFIED FIELD: Set blank=True to allow save() to fill it 🌟
    # Removed null=True and help_text referencing the old conditional unique constraint
    slug = models.SlugField(max_length=320, blank=True) 
    
    lesson_type = models.CharField(max_length=32, choices=LESSON_TYPE_CHOICES, default='video')
    summary = models.TextField(blank=True)
    body = models.TextField(blank=True, help_text="Optional HTML/markdown stored as text")
    position = models.PositiveIntegerField(default=0)
    duration_seconds = models.PositiveIntegerField(blank=True, null=True)
    required = models.BooleanField(default=True)

    media = models.ManyToManyField(MediaAsset, blank=True, related_name='lessons')

    class Meta:
        ordering = ["position"]
        constraints = [
            UniqueConstraint(fields=('module', 'position'), name='unique_lesson_position_per_module'),
            # 🌟 SIMPLIFIED CONSTRAINT: Slug is now always required and unique per module 🌟
            UniqueConstraint(fields=('module', 'slug'), name='unique_lesson_slug_per_module'),
        ]
        indexes = [
            models.Index(fields=["module", "position"]),
        ]

    def __str__(self):
        return f"{self.module.course.title} — {self.title}"

    def save(self, *args, **kwargs):
        # Store original title to detect changes for slug regeneration
        original_title = getattr(self, '__original_title', None)
        if not self.pk or self.title != original_title:            
            base_slug = slugify(self.title)
            unique_slug = base_slug
            num = 1
            while Lesson.objects.filter(module=self.module, slug=unique_slug).exclude(pk=self.pk).exists():
                unique_slug = f'{base_slug}-{num}'
                num += 1
            self.slug = unique_slug
        # Update original title storage and call parent save
        self.__original_title = self.title
        super().save(*args, **kwargs)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Store original title on initialization
        self.__original_title = self.title


# ---------- Facilitator-owned ----------
class CourseDraft(TimeStampedModel):
    DRAFT_STATUS = [
        ('draft', 'Draft'),
        ('submitted', 'Submitted for Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    DIFFICULTY_STATUS = [
        ('basic', 'Basic'),
        ('intermediate', 'Intermediate'),
        ('advanced', 'Advanced'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_by = models.ForeignKey(User,on_delete=models.CASCADE,related_name='course_drafts')

    title = models.CharField(max_length=300)
    slug = models.SlugField(max_length=300, unique=True)
    short_description = models.CharField(max_length=512, blank=True)
    long_description = models.TextField(blank=True)

    category = models.ForeignKey(CourseCategory,on_delete=models.SET_NULL, null=True,blank=True)
    tags = models.ManyToManyField(CourseTag, blank=True)

    thumbnail = models.ImageField(upload_to='learn/course_drafts/',blank=True, null=True)

    difficulty = models.CharField(max_length=50, choices=DIFFICULTY_STATUS, blank=True, null=True)

    status = models.CharField(max_length=20, choices=DRAFT_STATUS, default='draft', db_index=True)

    review_notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['created_by', 'status']),
        ]

    def __str__(self):
        return f"Draft: {self.title} ({self.status})"


class DraftModule(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course_draft = models.ForeignKey(
        CourseDraft,
        on_delete=models.CASCADE,
        related_name='modules'
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['position']
        constraints = [
            UniqueConstraint(
                fields=['course_draft', 'position'],
                name='unique_draft_module_position'
            )
        ]


class DraftLesson(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    module = models.ForeignKey(
        DraftModule,
        on_delete=models.CASCADE,
        related_name='lessons'
    )

    title = models.CharField(max_length=255)
    lesson_type = models.CharField(
        max_length=32,
        choices=Lesson.LESSON_TYPE_CHOICES
    )
    summary = models.TextField(blank=True)
    body = models.TextField(blank=True)
    position = models.PositiveIntegerField(default=0)
    duration_seconds = models.PositiveIntegerField(blank=True, null=True)

    media = models.ManyToManyField(MediaAsset, blank=True)

    class Meta:
        ordering = ['position']
        constraints = [
            UniqueConstraint(
                fields=['module', 'position'],
                name='unique_draft_lesson_position'
            )
        ]


# ---------- Assessments ----------

class Quiz(TimeStampedModel):
    """Quiz can be attached to a lesson or a module (module-level quiz via module FK)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    instructions = models.TextField(blank=True)
    time_limit_seconds = models.PositiveIntegerField(blank=True, null=True)
    max_attempts = models.PositiveIntegerField(default=3)
    randomize_questions = models.BooleanField(default=False)
    # quiz may be embedded in a lesson or associated to a module (module-level quiz)
    lesson = models.OneToOneField(Lesson, on_delete=models.CASCADE, null=True, blank=True, related_name='quiz')
    module = models.ForeignKey(Module, on_delete=models.CASCADE, null=True, blank=True, related_name='quizzes')

    class Meta:
        indexes = [
            models.Index(fields=["time_limit_seconds"]),
        ]

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
    points = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('1.00'))
    position = models.PositiveIntegerField(default=0)
    explanation = models.TextField(blank=True, null=True, help_text="Instructor explanation or solution")

    class Meta:
        ordering = ["position"]
        indexes = [
            models.Index(fields=["quiz", "position"]),
        ]

    def __str__(self):
        return f"Q: {self.prompt[:60]}"


class Option(models.Model):
    """Option for MCQ/Multi questions."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='options')
    text = models.CharField(max_length=1000)
    is_correct = models.BooleanField(default=False)
    position = models.PositiveIntegerField(default=0)
    feedback = models.CharField(max_length=500, blank=True, null=True, help_text="Optional per-option feedback")

    class Meta:
        ordering = ["position"]
        indexes = [
            models.Index(fields=["question", "position"]),
        ]

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
        # started_at included in uniqueness to allow multiple distinct attempts
        constraints = [
            UniqueConstraint(fields=("learner", "quiz", "started_at"), name='unique_quiz_attempt_per_start')
        ]

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
    progress_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'),
                                           validators=[MinValueValidator(Decimal('0.00')),
                                                       MaxValueValidator(Decimal('100.00'))])
    # In case of monetization:
    paid = models.BooleanField(default=False)

    # analytics fields
    completed_at = models.DateTimeField(null=True, blank=True)
    last_accessed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            UniqueConstraint(fields=("learner", "course"), name='unique_enrollment_per_learner_course')
        ]
        indexes = [
            models.Index(fields=["learner", "course"]),
            models.Index(fields=["status", "enrolled_at"]),
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
    first_opened_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    time_spent_seconds = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            UniqueConstraint(fields=("enrollment", "lesson"), name='unique_progress_per_enrollment_lesson')
        ]
        indexes = [
            models.Index(fields=["enrollment", "lesson"]),
            models.Index(fields=["completed", "completed_at"]),
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

    # revocation support
    revoked = models.BooleanField(default=False)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_reason = models.TextField(blank=True, null=True)

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
    is_deleted = models.BooleanField(default=False, help_text="Soft delete flag for moderation")

    class Meta:
        ordering = ["-pinned", "-created_at"]
        indexes = [
            models.Index(fields=["course", "pinned"]),
        ]

    def __str__(self):
        return f"Thread({self.title[:60]})"


class DiscussionReply(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    thread = models.ForeignKey(DiscussionThread, on_delete=models.CASCADE, related_name='replies')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='replies_created')
    body = models.TextField()
    parent = models.ForeignKey('self', null=True, blank=True, related_name='children', on_delete=models.CASCADE)
    is_deleted = models.BooleanField(default=False, help_text="Soft delete flag for moderation")

    class Meta:
        indexes = [
            models.Index(fields=["thread", "created_at"]),
        ]

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
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='feedbacks') # relate to Courses
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


# ---------- Learning Paths (Future Features) ----------

class LearningPath(TimeStampedModel):
    """A learning path that groups multiple courses into a recommended progression."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    courses = models.ManyToManyField(Course, through='LearningPathCourse', related_name='learning_paths')
    published = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["title"]

    def __str__(self):
        return self.title


class LearningPathCourse(models.Model):
    """Ordering join table for courses in a learning path."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    learning_path = models.ForeignKey(LearningPath, on_delete=models.CASCADE, related_name='path_courses')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='in_paths')
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["position"]
        constraints = [
            UniqueConstraint(fields=['learning_path', 'course'], name='unique_course_in_learningpath'),
            UniqueConstraint(fields=['learning_path', 'position'], name='unique_position_in_learningpath')
        ]
        indexes = [
            models.Index(fields=["learning_path", "position"]),
        ]

    def __str__(self):
        return f"{self.learning_path.title} — {self.course.title}"


class LearningPathProgress(TimeStampedModel):
    """Tracks a learner's progress through a learning path."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    learner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='path_progress')
    learning_path = models.ForeignKey(LearningPath, on_delete=models.CASCADE, related_name='progress')
    enrolled_at = models.DateTimeField(auto_now_add=True)
    progress_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'),
                                           validators=[MinValueValidator(Decimal('0.00')),
                                                       MaxValueValidator(Decimal('100.00'))])
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            UniqueConstraint(fields=['learner', 'learning_path'], name='unique_path_progress_per_learner')
        ]
        indexes = [
            models.Index(fields=["learner", "learning_path"]),
        ]

    def __str__(self):
        return f"PathProgress({self.learner_id}, {self.learning_path.title})"


# ---------- Cohorts (Session-based) ----------

class Cohort(TimeStampedModel):
    """A cohort (session) for a course. Facilitators can create cohorts with schedules/deadlines."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='cohorts')
    title = models.CharField(max_length=255)
    facilitator = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='cohorts_led')
    start_date = models.DateTimeField(null=True, blank=True)
    end_date = models.DateTimeField(null=True, blank=True)
    capacity = models.PositiveIntegerField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True,
                                help_text="Free-form schedule info, deadlines, timezone, meeting links etc.")
    published = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=["course", "start_date"]),
        ]

    def __str__(self):
        return f"Cohort({self.course.title} — {self.title})"


class CohortMembership(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cohort = models.ForeignKey(Cohort, on_delete=models.CASCADE, related_name='memberships')
    learner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='cohort_memberships')
    joined_at = models.DateTimeField(auto_now_add=True)
    role = models.CharField(max_length=32, default='learner', help_text="learner | ta | observer")

    class Meta:
        constraints = [
            UniqueConstraint(fields=['cohort', 'learner'], name='unique_cohort_membership')
        ]
        indexes = [
            models.Index(fields=["cohort", "learner"]),
        ]

    def __str__(self):
        return f"CohortMembership({self.cohort_id}, {self.learner_id})"


# ---------- Assignments & Peer Review ----------

class Assignment(TimeStampedModel):
    """
    Assignments can be optional for a course/module/lesson.
    At least one of course/module/lesson should be set (enforced in app-level validation).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='assignments', null=True, blank=True)
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name='assignments', null=True, blank=True)
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name='assignments', null=True, blank=True)
    due_date = models.DateTimeField(null=True, blank=True)
    points = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal('100.00'))
    peer_review_enabled = models.BooleanField(default=False)
    peer_review_count = models.PositiveIntegerField(default=0,
                                                   help_text="Number of peer reviews required (if enabled)")
    allow_late_submissions = models.BooleanField(default=True)
    # rubric and other metadata
    rubric = models.JSONField(default=dict, blank=True, help_text="Structured rubric for grading")
    published = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=["course", "module", "lesson"]),
        ]

    def __str__(self):
        return self.title


class Submission(TimeStampedModel):
    """Learner submission for an assignment."""
    STATUS_CHOICES = [
        ('submitted', 'Submitted'),
        ('graded', 'Graded'),
        ('late', 'Late'),
        ('resubmitted', 'Resubmitted'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name='submissions')
    learner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='submissions')
    submitted_at = models.DateTimeField(auto_now_add=True)
    content = models.TextField(blank=True, help_text="Optional textual submission or description")
    files = models.FileField(upload_to='learn/assignments/', null=True, blank=True)
    grade = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    grader = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='graded_submissions')
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default='submitted')
    feedback = models.TextField(blank=True, null=True)
    meta = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            UniqueConstraint(fields=['assignment', 'learner'], name='unique_submission_per_assignment_learner')
        ]
        indexes = [
            models.Index(fields=["assignment", "learner", "submitted_at"]),
        ]

    def __str__(self):
        return f"Submission({self.assignment_id}, {self.learner_id})"


class PeerReview(TimeStampedModel):
    """Peer review record for a submission (if peer review enabled)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    submission = models.ForeignKey(Submission, on_delete=models.CASCADE, related_name='peer_reviews')
    reviewer = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='peer_reviews_given')
    reviewed_at = models.DateTimeField(auto_now_add=True)
    score = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    comments = models.TextField(blank=True)
    meta = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["submission", "reviewer"]),
        ]

    def __str__(self):
        return f"PeerReview({self.submission_id}, {self.reviewer_id})"


"""
Notes & Next Steps (practical)

App-level validation: For Assignment ensure in clean() or serializer that at least one of course/module/lesson is set. I did not add DB-level constraint because it is complex to model across three fields.

Search updating: You already included SearchVectorField; add a management command or DB trigger to update it on save for searchable fields (title, short_description, long_description).

Denormalized counters: lessons_count, modules_count on Course should be maintained in signals or background tasks (Celery) for scale.

Peer review matching: You will need logic to assign peer reviewers (round-robin, random, or expert selected) and to prevent conflicts of interest.

Cohort scheduling: The metadata JSON field in Cohort is flexible for storing timelines, calendar ICS links, Zoom links, timezone info.

Indexes & constraints: I added several constraints and indexes for correctness and performance; adjust based on query patterns and DB explain plans.

If this looks good I will:

produce the admin.py registrations (with inlines and list filters) and/or

generate serializers + DRF views for CRUD + enrollment APIs, or

write migrations and a small data migration script to backfill slugs/search vectors.
"""



