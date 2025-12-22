from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from ..models import CourseDraft, DraftModule, Course
from ..forms import CourseDraftForm, DraftModuleForm, DraftLessonForm, MediaAssetForm
from django.db.models import Count # New import needed for aggregation


# kilaso@gmail.com


@login_required
def facilitator_dashboard(request):
    """
    Facilitator dashboard view, providing an overview of draft status and
    authored courses.
    """
    user = request.user
    
    # Get all status choices
    STATUS_CHOICES = [status[0] for status in CourseDraft.DRAFT_STATUS]
    status_summary = {status: 0 for status in STATUS_CHOICES}
    # 1. Draft Status Overview (A count of the facilitator's drafts by status)
    draft_status_counts = CourseDraft.objects.filter(created_by=user).values('status').annotate(count=Count('id'))
    
    # Transform the list of dicts into a more convenient dict: {'draft': 5, 'submitted': 2, ...}
    # 3. Update the summary with actual counts
    for item in draft_status_counts:
        status_summary[item['status']] = item['count']
    # status_summary = {item['status']: item['count'] for item in draft_status_counts}

    # 2. Recently Published Courses (If the facilitator has any live courses)
    # We use the public Course model here, checking for the user as a facilitator
    authored_courses = Course.objects.filter(facilitators=user).order_by('-published_at')[:5]

    # 3. List of Active Drafts (Currently being worked on)
    active_drafts = CourseDraft.objects.filter(
        created_by=user,
        status='draft'
    ).order_by('-updated_at')[:5]

    # 4. List of Submitted Drafts (Awaiting admin review)
    submitted_drafts = CourseDraft.objects.filter(
        created_by=user,
        status='submitted'
    ).order_by('-created_at')

    context = {
        'status_summary': status_summary,
        'active_drafts': active_drafts,
        'submitted_drafts': submitted_drafts,
        'authored_courses': authored_courses,
    }

    return render(request, 'learn/facilitator/dashboard.html', context)

# ------------- Draft Course (CRUD) ----------
@login_required
def facilitator_draft_list_view(request):
    drafts = CourseDraft.objects.filter(created_by=request.user)
    return render(request, 'learn/facilitator/draft_list.html', {
        'drafts': drafts
    })


@login_required
def facilitator_draft_create_view(request):
    if request.method == 'POST':
        form = CourseDraftForm(request.POST, request.FILES)
        if form.is_valid():
            draft = form.save(commit=False)
            draft.created_by = request.user
            draft.save()
            form.save_m2m()
            return redirect('learn:facilitator_draft_detail', draft.id)
    else:
        form = CourseDraftForm()

    return render(request, 'learn/facilitator/draft_form.html', {
        'form': form
    })


@login_required
def facilitator_draft_detail_view(request, pk):
    draft = get_object_or_404(
        CourseDraft,
        pk=pk,
        created_by=request.user
    )
    return render(request, 'learn/facilitator/draft_detail.html', {
        'draft': draft
    })


# ADD Module 
@login_required
def facilitator_module_create_view(request, draft_id):
    draft = get_object_or_404(
        CourseDraft,
        id=draft_id,
        created_by=request.user
    )

    if request.method == 'POST':
        form = DraftModuleForm(request.POST)
        if form.is_valid():
            module = form.save(commit=False)
            module.course_draft = draft
            module.save()
            return redirect('learn:facilitator_draft_detail', draft.id)
    else:
        form = DraftModuleForm()

    return render(request, 'learn/facilitator/module_form.html', {
        'form': form,
        'draft': draft
    })


# ADD Lesson
@login_required
def facilitator_lesson_create_view(request, module_id):
    module = get_object_or_404(
        DraftModule,
        id=module_id,
        course_draft__created_by=request.user
    )

    if request.method == 'POST':
        form = DraftLessonForm(request.POST)
        if form.is_valid():
            lesson = form.save(commit=False)
            lesson.module = module
            lesson.save()
            form.save_m2m()
            return redirect(
                'learn:facilitator_draft_detail',
                module.course_draft.id
            )
    else:
        form = DraftLessonForm()

    return render(request, 'learn/facilitator/lesson_form.html', {
        'form': form,
        'module': module
    })


# Media Upload
@login_required
def facilitator_media_upload_view(request):
    if request.method == 'POST':
        form = MediaAssetForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            return redirect(request.META.get('HTTP_REFERER', '/'))
    else:
        form = MediaAssetForm()

    return render(request, 'learn/facilitator/media_form.html', {
        'form': form
    })

