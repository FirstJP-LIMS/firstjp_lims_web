from django.shortcuts import get_object_or_404, render
from django.contrib.auth.decorators import login_required

from ..models import Module, Course, Lesson


def module_detail_view(request, module_id):
    """Display module with ordered lessons; enrolled learners can view lesson links."""
    module = get_object_or_404(Module.objects.select_related("course"), id=module_id)
    lessons = module.lessons.order_by("position").all()

    context = {
        "module": module,
        "course": module.course,
        "lessons": lessons,
    }
    return render(request, "learn/modules/module_detail.html", context)

