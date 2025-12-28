from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Count
from django.http import HttpResponse, FileResponse, JsonResponse
from django.utils import timezone
from django.core.paginator import Paginator
from datetime import timedelta
import hashlib

from .models import (
    DocumentCategory, ControlledDocument, DocumentVersion,
    DocumentReview, DocumentApproval, DocumentDistribution,
    DocumentTraining, DocumentAuditLog, DocumentReference
)

from .forms import (
    DocumentCategoryForm, ControlledDocumentForm, DocumentVersionForm,
    DocumentReviewForm, DocumentApprovalForm, DocumentDistributionForm,
    DocumentTrainingForm, DocumentAcknowledgmentForm, DocumentSearchForm,
    DocumentReferenceForm
)


def get_user_vendor(request):
    """Helper function to get current user's vendor"""
    if hasattr(request.user, 'vendor'):
        return request.user.vendor
    return None


def create_audit_log(document, action, user, description, request, old_value='', new_value=''):
    """Helper function to create audit log entries"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip_address = x_forwarded_for.split(',')[0]
    else:
        ip_address = request.META.get('REMOTE_ADDR', '0.0.0.0')
    
    DocumentAuditLog.objects.create(
        vendor=document.vendor,
        document=document,
        action=action,
        user=user,
        user_full_name=user.get_full_name() or user.username,
        description=description,
        old_value=old_value,
        new_value=new_value,
        ip_address=ip_address,
        user_agent=request.META.get('HTTP_USER_AGENT', '')[:255]
    )


# ============================================================================
# DASHBOARD & OVERVIEW
# ============================================================================

@login_required
def document_dashboard(request):
    """Document control dashboard with statistics and alerts"""
    vendor = get_user_vendor(request)
    
    if not vendor:
        messages.error(request, 'No vendor associated with your account.')
        return redirect('home')
    
    # Get statistics
    total_documents = ControlledDocument.objects.filter(vendor=vendor).count()
    effective_documents = ControlledDocument.objects.filter(
        vendor=vendor,
        status='effective'
    ).count()
    
    documents_due_review = ControlledDocument.objects.filter(
        vendor=vendor,
        status='effective',
        next_review_date__lte=timezone.now().date()
    ).count()
    
    pending_reviews = DocumentReview.objects.filter(
        vendor=vendor,
        status='pending'
    ).count()
    
    pending_approvals = DocumentReview.objects.filter(
        vendor=vendor,
        status='under_review',
        reviewer=request.user
    ).count()
    
    pending_acknowledgments = DocumentDistribution.objects.filter(
        vendor=vendor,
        distributed_to=request.user,
        requires_acknowledgment=True,
        acknowledged=False
    ).count()
    
    pending_trainings = DocumentTraining.objects.filter(
        vendor=vendor,
        trainee=request.user,
        status__in=['required', 'in_progress']
    ).count()
    
    # Recent documents
    recent_documents = ControlledDocument.objects.filter(
        vendor=vendor
    ).order_by('-created_at')[:10]
    
    # Documents due for review
    review_due_documents = ControlledDocument.objects.filter(
        vendor=vendor,
        status='effective',
        next_review_date__lte=timezone.now().date() + timedelta(days=30)
    ).order_by('next_review_date')[:10]
    
    # My pending tasks
    my_reviews = DocumentReview.objects.filter(
        vendor=vendor,
        reviewer=request.user,
        status__in=['pending', 'in_progress']
    ).order_by('due_date')[:5]
    
    my_acknowledgments = DocumentDistribution.objects.filter(
        vendor=vendor,
        distributed_to=request.user,
        acknowledged=False
    ).order_by('-distributed_at')[:5]
    
    context = {
        'total_documents': total_documents,
        'effective_documents': effective_documents,
        'documents_due_review': documents_due_review,
        'pending_reviews': pending_reviews,
        'pending_approvals': pending_approvals,
        'pending_acknowledgments': pending_acknowledgments,
        'pending_trainings': pending_trainings,
        'recent_documents': recent_documents,
        'review_due_documents': review_due_documents,
        'my_reviews': my_reviews,
        'my_acknowledgments': my_acknowledgments,
    }
    
    return render(request, 'documents/dashboard.html', context)
    # return render(request, 'doc_control/dashboard.html', context)


# ========================================================
# DOCUMENT CATEGORY VIEWS
# ========================================================

@login_required
def category_list(request):
    """List all document categories"""
    vendor = get_user_vendor(request)
    
    categories = DocumentCategory.objects.filter(vendor=vendor)
    
    # Add document counts
    categories = categories.annotate(
        document_count=Count('documents')
    )
    
    context = {
        'categories': categories
    }
    
    return render(request, 'documents/category/category_list.html', context)


@login_required
def category_create(request):
    """Create new document category"""
    vendor = get_user_vendor(request)
    
    if request.method == 'POST':
        form = DocumentCategoryForm(request.POST, vendor=vendor)
        if form.is_valid():
            category = form.save(commit=False)
            category.vendor = vendor
            category.created_by = request.user
            category.save()
            
            messages.success(request, f'Category "{category.name}" created successfully.')
            return redirect('documents:category_list')
    else:
        form = DocumentCategoryForm(vendor=vendor)
    
    context = {
        'form': form,
        'title': 'Create Document Category',
    }
    
    return render(request, 'documents/category/category_form.html', context)


@login_required
def category_detail(request, pk):
    """View category details and associated documents"""
    vendor = get_user_vendor(request)
    category = get_object_or_404(DocumentCategory, pk=pk, vendor=vendor)
    
    # Get documents in this category
    documents = ControlledDocument.objects.filter(
        vendor=vendor,
        category=category
    ).order_by('-created_at')
    
    # Statistics
    total_documents = documents.count()
    effective_documents = documents.filter(status='effective').count()
    draft_documents = documents.filter(status='draft').count()
    under_review_documents = documents.filter(status='under_review').count()
    
    # Documents by status
    status_breakdown = documents.values('status').annotate(
        count=Count('id')
    )
    
    # Pagination
    paginator = Paginator(documents, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'category': category,
        'page_obj': page_obj,
        'total_documents': total_documents,
        'effective_documents': effective_documents,
        'draft_documents': draft_documents,
        'under_review_documents': under_review_documents,
        'status_breakdown': status_breakdown,
    }
    
    return render(request, 'documents/category/category_detail.html', context)


@login_required
def category_edit(request, pk):
    """Edit document category"""
    vendor = get_user_vendor(request)
    category = get_object_or_404(DocumentCategory, pk=pk, vendor=vendor)
    
    if request.method == 'POST':
        form = DocumentCategoryForm(request.POST, instance=category, vendor=vendor)
        if form.is_valid():
            form.save()
            messages.success(request, f'Category "{category.name}" updated successfully.')
            return redirect('documents:category_list')
    else:
        form = DocumentCategoryForm(instance=category, vendor=vendor)
    
    context = {
        'form': form,
        'category': category,
        'title': 'Edit Document Category'
    }
    
    return render(request, 'documents/category/category_form.html', context)


# ========================================================
# CONTROLLED DOCUMENT VIEWS
# ======================================================

@login_required
def document_list(request):
    """List all controlled documents with search and filtering"""
    vendor = get_user_vendor(request)
    
    documents = ControlledDocument.objects.filter(vendor=vendor)
    
    # Search and filtering
    search_form = DocumentSearchForm(request.GET, vendor=vendor)
    
    if search_form.is_valid():
        query = search_form.cleaned_data.get('query')
        category = search_form.cleaned_data.get('category')
        status = search_form.cleaned_data.get('status')
        owner = search_form.cleaned_data.get('owner')
        date_from = search_form.cleaned_data.get('date_from')
        date_to = search_form.cleaned_data.get('date_to')
        
        if query:
            documents = documents.filter(
                Q(document_number__icontains=query) |
                Q(title__icontains=query) |
                Q(keywords__icontains=query)
            )
        
        if category:
            documents = documents.filter(category=category)
        
        if status:
            documents = documents.filter(status=status)
        
        if owner:
            documents = documents.filter(owner=owner)
        
        if date_from:
            documents = documents.filter(created_at__gte=date_from)
        
        if date_to:
            documents = documents.filter(created_at__lte=date_to)
    
    # Pagination
    paginator = Paginator(documents.order_by('-created_at'), 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'search_form': search_form,
        'total_count': documents.count()
    }
    
    return render(request, 'documents/document/document_list.html', context)


@login_required
def document_detail(request, pk):
    """View document details"""
    vendor = get_user_vendor(request)
    document = get_object_or_404(ControlledDocument, pk=pk, vendor=vendor)
    
    # Create audit log for viewing
    create_audit_log(
        document=document,
        action='viewed',
        user=request.user,
        description=f'Document viewed by {request.user.get_full_name()}',
        request=request
    )
    
    # Get related data
    versions = document.versions.all().order_by('-created_at')[:10]
    reviews = document.reviews.all().order_by('-created_at')[:5]
    approvals = document.approvals.all().order_by('-signed_at')[:5]
    distributions = document.distributions.all().order_by('-distributed_at')[:10]
    trainings = document.trainings.all().order_by('-assigned_at')[:10]
    audit_logs = document.audit_logs.all().order_by('-timestamp')[:20]
    references = document.references_made.all()

    # Process keywords
    keywords = []
    if document.keywords:
        keywords = [k.strip() for k in document.keywords.split(',') if k.strip()]

    context = {
        'document': document,
        'versions': versions,
        'keywords': keywords,
        'reviews': reviews,
        'approvals': approvals,
        'distributions': distributions,
        'trainings': trainings,
        'audit_logs': audit_logs,
        'references': references,
    }
 
    return render(request, 'documents/document/document_detail.html', context)


@login_required
def document_create(request):
    """Create new controlled document"""
    vendor = get_user_vendor(request)
    
    if request.method == 'POST':
        form = ControlledDocumentForm(
            request.POST,
            request.FILES,
            vendor=vendor,
            user=request.user
        )
        if form.is_valid():
            document = form.save(commit=False)
            document.vendor = vendor
            document.created_by = request.user
            document.updated_by = request.user
            document.save()
            
            # Create audit log
            create_audit_log(
                document=document,
                action='created',
                user=request.user,
                description=f'Document created by {request.user.get_full_name()}',
                request=request
            )
            
            messages.success(request, f'Document "{document.title}" created successfully.')
            return redirect('documents:document_detail', pk=document.pk)
    else:
        form = ControlledDocumentForm(vendor=vendor, user=request.user)
    
    context = {
        'form': form,
        'title': 'Create Controlled Document'
    }
    
    return render(request, 'documents/document/document_form.html', context)


@login_required
def document_edit(request, pk):
    """Edit controlled document"""
    vendor = get_user_vendor(request)
    document = get_object_or_404(ControlledDocument, pk=pk, vendor=vendor)
    
    # Store old values for audit
    old_data = {
        'title': document.title,
        'status': document.status,
        'version': document.version
    }
    
    if request.method == 'POST':
        form = ControlledDocumentForm(
            request.POST,
            request.FILES,
            instance=document,
            vendor=vendor,
            user=request.user
        )
        if form.is_valid():
            document = form.save(commit=False)
            document.updated_by = request.user
            document.save()
            
            # Create audit log
            changes = []
            if old_data['title'] != document.title:
                changes.append(f"Title changed from '{old_data['title']}' to '{document.title}'")
            if old_data['status'] != document.status:
                changes.append(f"Status changed from '{old_data['status']}' to '{document.status}'")
            
            create_audit_log(
                document=document,
                action='updated',
                user=request.user,
                description=f'Document updated: {", ".join(changes) if changes else "Minor updates"}',
                request=request
            )
            
            messages.success(request, f'Document "{document.title}" updated successfully.')
            return redirect('documents:document_detail', pk=document.pk)
    else:
        form = ControlledDocumentForm(instance=document, vendor=vendor, user=request.user)
    
    context = {
        'form': form,
        'document': document,
        'title': 'Edit Document'
    }
    
    return render(request, 'documents/document/document_form.html', context)


@login_required
def document_download(request, pk):
    """Download document file uploaded by the laboratory."""
    vendor = get_user_vendor(request)
    document = get_object_or_404(ControlledDocument, pk=pk, vendor=vendor)
    
    if not document.file:
        messages.error(request, 'No file attached to this document.')
        return redirect('documents:document_detail', pk=pk)
    
    # Create audit log
    create_audit_log(
        document=document,
        action='downloaded',
        user=request.user,
        description=f'Document downloaded by {request.user.get_full_name()}',
        request=request
    )
    
    response = FileResponse(document.file.open('rb'))
    response['Content-Disposition'] = f'attachment; filename="{document.get_full_identifier()}.pdf"'
    
    return response


# ======================================================
# VERSION CONTROL VIEWS
# ======================================================

@login_required
def version_create(request, document_pk):
    """Create new version of document"""
    vendor = get_user_vendor(request)
    document = get_object_or_404(ControlledDocument, pk=document_pk, vendor=vendor)
    
    if request.method == 'POST':
        form = DocumentVersionForm(
            request.POST,
            request.FILES,
            document=document,
            vendor=vendor
        )
        if form.is_valid():
            version = form.save(commit=False)
            version.created_by = request.user
            version.save()
            
            # Update main document version
            document.version = version.version_number
            document.save()
            
            # Create audit log
            create_audit_log(
                document=document,
                action='updated',
                user=request.user,
                description=f'New version {version.version_number} created: {version.change_description}',
                request=request,
                old_value=document.version,
                new_value=version.version_number
            )
            
            messages.success(request, f'Version {version.version_number} created successfully.')
            return redirect('documents:document_detail', pk=document.pk)
    else:
        form = DocumentVersionForm(document=document, vendor=vendor)
    
    context = {
        'form': form,
        'document': document,
        'title': f'Create New Version for {document.document_number}'
    }
    
    return render(request, 'documents/version/version_form.html', context)


@login_required
def version_list(request, document_pk):
    """View all versions of a document"""
    vendor = get_user_vendor(request)
    document = get_object_or_404(ControlledDocument, pk=document_pk, vendor=vendor)
    
    versions = document.versions.all().order_by('-created_at')
    
    context = {
        'document': document,
        'versions': versions
    }
    
    return render(request, 'documents/version/version_list.html', context)


# ===========================================
# REVIEW & APPROVAL VIEWS
# ===========================================

@login_required
def review_list(request):
    """List all document reviews"""
    vendor = get_user_vendor(request)
    
    reviews = DocumentReview.objects.filter(vendor=vendor)
    
    # Filter by status
    status_filter = request.GET.get('status')
    if status_filter:
        reviews = reviews.filter(status=status_filter)
    
    # Show only my reviews if requested
    my_reviews_only = request.GET.get('my_reviews')
    if my_reviews_only:
        reviews = reviews.filter(
            Q(reviewer=request.user) | Q(approver=request.user)
        )
    
    reviews = reviews.order_by('-created_at')
    
    # Pagination
    paginator = Paginator(reviews, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'status_filter': status_filter,
        'status_choices': DocumentReview.REVIEW_STATUS_CHOICES,
        'reviews': reviews,  # The unfiltered queryset for stats
    }
    
    return render(request, 'documents/review/review_list.html', context)


@login_required
def review_create(request, document_pk=None):
    """Create new document review"""
    vendor = get_user_vendor(request)
    document = None
    
    if document_pk:
        document = get_object_or_404(ControlledDocument, pk=document_pk, vendor=vendor)
    
    if request.method == 'POST':
        form = DocumentReviewForm(request.POST, vendor=vendor)
        if form.is_valid():
            review = form.save(commit=False)
            review.vendor = vendor
            review.created_by = request.user
            review.save()
            
            messages.success(request, 'Review created and assigned successfully.')
            return redirect('documents:review_list')
    else:
        initial = {}
        if document:
            initial['document'] = document
        form = DocumentReviewForm(initial=initial, vendor=vendor)
    
    context = {
        'form': form,
        'document': document,
        'title': 'Create Document Review'
    }
    
    return render(request, 'documents/review/review_form.html', context)


@login_required
def review_detail(request, pk):
    """View review details and approve/reject"""
    vendor = get_user_vendor(request)
    review = get_object_or_404(DocumentReview, pk=pk, vendor=vendor)
    
    # Check if user is reviewer or approver
    is_reviewer = review.reviewer == request.user
    is_approver = review.approver == request.user if review.approver else False
    
    context = {
        'review': review,
        'is_reviewer': is_reviewer,
        'is_approver': is_approver,
    }
    
    return render(request, 'documents/review/review_detail.html', context)


@login_required
def document_approve(request, pk):
    """Approve document with electronic signature"""
    vendor = get_user_vendor(request)
    document = get_object_or_404(ControlledDocument, pk=pk, vendor=vendor)
    
    if request.method == 'POST':
        form = DocumentApprovalForm(
            request.POST,
            user=request.user,
            request=request
        )
        if form.is_valid():
            approval = form.save(commit=False)
            approval.vendor = vendor
            approval.document = document
            approval.save()
            
            # Update document status if approved
            if approval.approval_status == 'approved':
                document.status = 'approved'
                document.save()
            
            # Create audit log
            create_audit_log(
                document=document,
                action='approved',
                user=request.user,
                description=f'Document {approval.get_approval_status_display()} by {request.user.get_full_name()}',
                request=request
            )
            
            messages.success(request, f'Document {approval.get_approval_status_display().lower()} successfully.')
            return redirect('documents:document_detail', pk=document.pk)
    else:
        form = DocumentApprovalForm(user=request.user, request=request)
    
    context = {
        'form': form,
        'document': document,
        'title': 'Approve Document'
    }
    
    return render(request, 'documents/review/approval_form.html', context)


# =================================================
# DISTRIBUTION VIEWS
# =================================================

@login_required
def distribution_create(request, document_pk):
    """Distribute document to users"""
    vendor = get_user_vendor(request)
    document = get_object_or_404(ControlledDocument, pk=document_pk, vendor=vendor)
    
    if request.method == 'POST':
        form = DocumentDistributionForm(
            request.POST,
            vendor=vendor,
            document=document
        )
        if form.is_valid():
            users = form.cleaned_data.get('users')
            distribution_method = form.cleaned_data.get('distribution_method')
            requires_acknowledgment = form.cleaned_data.get('requires_acknowledgment')
            
            # Create distribution records for each user
            for user in users:
                DocumentDistribution.objects.create(
                    vendor=vendor,
                    document=document,
                    distributed_to=user,
                    distribution_method=distribution_method,
                    requires_acknowledgment=requires_acknowledgment,
                    distributed_by=request.user
                )
            
            # Create audit log
            create_audit_log(
                document=document,
                action='distributed',
                user=request.user,
                description=f'Document distributed to {users.count()} user(s)',
                request=request
            )
            
            messages.success(request, f'Document distributed to {users.count()} user(s) successfully.')
            return redirect('documents:document_detail', pk=document.pk)
    else:
        form = DocumentDistributionForm(vendor=vendor, document=document)
    
    context = {
        'form': form,
        'document': document,
        'title': 'Distribute Document'
    }
    
    return render(request, 'documents/distribution/distribution_form.html', context)


@login_required
def document_acknowledge(request, distribution_pk):
    """Acknowledge receipt of document"""
    vendor = get_user_vendor(request)
    distribution = get_object_or_404(
        DocumentDistribution,
        pk=distribution_pk,
        vendor=vendor,
        distributed_to=request.user
    )
    
    if distribution.acknowledged:
        messages.info(request, 'You have already acknowledged this document.')
        return redirect('documents:document_detail', pk=distribution.document.pk)
    
    if request.method == 'POST':
        form = DocumentAcknowledgmentForm(request.POST, user=request.user)
        if form.is_valid():
            # Create signature
            signature_string = f"{request.user.username}_{timezone.now().isoformat()}"
            signature = hashlib.sha256(signature_string.encode()).hexdigest()
            
            distribution.acknowledged = True
            distribution.acknowledged_at = timezone.now()
            distribution.acknowledgment_signature = signature
            distribution.save()
            
            messages.success(request, 'Document acknowledged successfully.')
            return redirect('documents:document_detail', pk=distribution.document.pk)
    else:
        form = DocumentAcknowledgmentForm(user=request.user)
    
    context = {
        'form': form,
        'distribution': distribution,
        'document': distribution.document,
        'title': 'Acknowledge Document'
    }
    
    return render(request, 'documents/distribution/acknowledgment_form.html', context)


# =======================================
# TRAINING VIEWS
# =======================================

@login_required
def training_list(request):
    """List all training records"""
    vendor = get_user_vendor(request)
    
    trainings = DocumentTraining.objects.filter(vendor=vendor)
    
    # Show only my trainings if requested
    my_trainings = request.GET.get('my_trainings')
    if my_trainings:
        trainings = trainings.filter(trainee=request.user)
    
    trainings = trainings.order_by('-assigned_at')
    
    # Pagination
    paginator = Paginator(trainings, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj
    }
    
    return render(request, 'documents/training/training_list.html', context)


@login_required
def training_assign(request, document_pk):
    """Assign training to users"""
    vendor = get_user_vendor(request)
    document = get_object_or_404(ControlledDocument, pk=document_pk, vendor=vendor)
    
    if request.method == 'POST':
        form = DocumentTrainingForm(
            request.POST,
            vendor=vendor,
            document=document
        )
        if form.is_valid():
            trainees = form.cleaned_data.get('trainees')
            training_type = form.cleaned_data.get('training_type')
            
            if trainees:
                # Create training records for multiple users
                for trainee in trainees:
                    DocumentTraining.objects.create(
                        vendor=vendor,
                        document=document,
                        trainee=trainee,
                        training_type=training_type,
                        assigned_by=request.user
                    )
                
                messages.success(
                    request,
                    f'Training assigned to {trainees.count()} user(s) successfully.'
                )
            else:
                # Single training record
                training = form.save(commit=False)
                training.vendor = vendor
                training.document = document
                training.assigned_by = request.user
                training.save()
                
                messages.success(request, 'Training assigned successfully.')
            
            return redirect('documents:document_detail', pk=document.pk)
    else:
        form = DocumentTrainingForm(vendor=vendor, document=document)
    
    context = {
        'form': form,
        'document': document,
        'title': 'Assign Training'
    }
    
    return render(request, 'documents/training/training_form.html', context)


# ========================================
# REFERENCE VIEWS
# ========================================

@login_required
def reference_create(request, document_pk):
    """Create document reference"""
    vendor = get_user_vendor(request)
    document = get_object_or_404(ControlledDocument, pk=document_pk, vendor=vendor)
    
    if request.method == 'POST':
        form = DocumentReferenceForm(
            request.POST,
            vendor=vendor,
            source_document=document
        )
        if form.is_valid():
            reference = form.save(commit=False)
            reference.vendor = vendor
            reference.source_document = document
            reference.created_by = request.user
            reference.save()
            
            messages.success(request, 'Document reference created successfully.')
            return redirect('documents:document_detail', pk=document.pk)
    else:
        form = DocumentReferenceForm(vendor=vendor, source_document=document)
    
    context = {
        'form': form,
        'document': document,
        'title': 'Add Document Reference'
    }
    
    return render(request, 'documents/reference/reference_form.html', context)


# ============================================
# REPORTS & ANALYTICS
# ============================================

@login_required
def document_reports(request):
    """Generate document control reports"""
    vendor = get_user_vendor(request)
    
    # Statistics
    total_docs = ControlledDocument.objects.filter(vendor=vendor).count()
    effective_docs = ControlledDocument.objects.filter(
        vendor=vendor,
        status='effective'
    ).count()
    
    # Documents by category
    docs_by_category = DocumentCategory.objects.filter(vendor=vendor).annotate(
        doc_count=Count('documents')
    )
    
    # Documents by status
    docs_by_status = ControlledDocument.objects.filter(vendor=vendor).values(
        'status'
    ).annotate(count=Count('id'))
    
    # Overdue reviews
    overdue_reviews = DocumentReview.objects.filter(
        vendor=vendor,
        status='pending',
        due_date__lt=timezone.now().date()
    ).count()
    
    context = {
        'total_docs': total_docs,
        'effective_docs': effective_docs,
        'docs_by_category': docs_by_category,
        'docs_by_status': docs_by_status,
        'overdue_reviews': overdue_reviews,
    }
    
    return render(request, 'documents/report/report.html', context)

