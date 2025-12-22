# apps/learn/services/course_promotion.py
from django.utils import timezone
from ..models import Module, Course, Lesson


def promote_course_draft(draft):
    course = Course.objects.create(
        title=draft.title,
        slug=draft.slug,
        short_description=draft.short_description,
        long_description=draft.long_description,
        category=draft.category,
        difficulty=draft.difficulty,
        published=True,
        published_at=timezone.now(),
    )

    course.tags.set(draft.tags.all())
    course.facilitators.add(draft.created_by)

    for dm in draft.modules.all():
        module = Module.objects.create(
            course=course,
            title=dm.title,
            description=dm.description,
            position=dm.position,
        )

        for dl in dm.lessons.all():
            lesson = Lesson.objects.create(
                module=module,
                title=dl.title,
                lesson_type=dl.lesson_type,
                summary=dl.summary,
                body=dl.body,
                position=dl.position,
                duration_seconds=dl.duration_seconds,
            )
            lesson.media.set(dl.media.all())

    draft.status = 'approved'
    draft.save(update_fields=['status'])

    return course

