from django.db import models
from django.conf import settings # Use settings.AUTH_USER_MODEL for User FK
from apps.core.managers import TenantAwareManager # Keep TenantAwareManager if needed for related models
from apps.tenants.models import Vendor # Only if tracking a vendor's *use* of a course, not the course itself

# ------------------------------------------------
# Facilitator Model (Links User to Instructor Role)
# ------------------------------------------------
class Facilitator(models.Model):
    """
    Represents a platform user who has been designated as an instructor.
    This links the global course content to an internal staff member.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='facilitator_profile'
    )
    bio = models.TextField(blank=True, verbose_name="Instructor Biography")
    is_active = models.BooleanField(default=True)
    
    # Note: No 'vendor' field here, as the content they teach is platform-global.
    
    def __str__(self):
        return self.user.get_full_name() or self.user.email

# ------------------------------------------------
# Course Model (Platform-Global)
# ------------------------------------------------
class Course(models.Model):
    """Platform-owned courses available to all tenants/users."""
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    description = models.TextField()
    facilitator = models.ForeignKey(Facilitator, on_delete=models.SET_NULL, null=True, related_name='courses')
    is_published = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['title']

    def __str__(self):
        return self.title

# ------------------------------------------------
# Lesson Model (Platform-Global)
# ------------------------------------------------
class Lesson(models.Model):
    """Individual modules or topics within a Course."""
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='lessons')
    title = models.CharField(max_length=255)
    content = models.TextField(help_text="HTML or rich text content of the lesson.")
    video_url = models.URLField(blank=True, null=True)
    order = models.PositiveSmallIntegerField(default=0) # For lesson sequence
    
    class Meta:
        ordering = ['order']
        unique_together = ('course', 'order')

    def __str__(self):
        return f"{self.course.title}: {self.title}"

# ------------------------------------------------
# Enrollment Model (Tenant-Aware Usage Tracking)
# ------------------------------------------------
# This model tracks a tenant's user taking a global course.
class Enrollment(models.Model):
    """Tracks which user (and implicitly, which tenant) is enrolled in which course."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='enrollments')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='enrollments')
    enrolled_on = models.DateTimeField(auto_now_add=True)
    completed_lessons = models.ManyToManyField(Lesson, blank=True)
    
    # We can use the TenantAwareManager here to scope enrollments if needed, 
    # but since the User model already scopes to a Vendor, it's often redundant.
    # objects = TenantAwareManager() 
    
    class Meta:
        unique_together = ('user', 'course')
        # We can enforce that the user must belong to a vendor to enroll 
        # (based on your User model design)
        
    def __str__(self):
        return f"{self.user.email} enrolled in {self.course.title}"
    
