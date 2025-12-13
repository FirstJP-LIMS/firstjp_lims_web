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


# ============================================================================
# DOCUMENT CATEGORY VIEWS
# ============================================================================

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
    
    return render(request, 'documents/category_list.html', context)


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
        'title': 'Create Document Category'
    }
    
    return render(request, 'documents/category_form.html', context)


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
    
    return render(request, 'documents/category_form.html', context)


# ============================================================================
# CONTROLLED DOCUMENT VIEWS
# ============================================================================

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
    
    return render(request, 'documents/document_list.html', context)


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
    
    context = {
        'document': document,
        'versions': versions,
        'reviews': reviews,
        'approvals': approvals,
        'distributions': distributions,
        'trainings': trainings,
        'audit_logs': audit_logs,
        'references': references,
    }
    
    return render(request, 'documents/document_detail.html', context)


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
    
    return render(request, 'documents/document_form.html', context)


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
    
    return render(request, 'documents/document_form.html', context)


@login_required
def document_download(request, pk):
    """Download document file"""
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


# ============================================================================
# VERSION CONTROL VIEWS
# ============================================================================

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
    
    return render(request, 'documents/version_form.html', context)


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
    
    return render(request, 'documents/version_list.html', context)


# ============================================================================
# REVIEW & APPROVAL VIEWS
# ============================================================================

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
        'status_filter': status_filter
    }
    
    return render(request, 'documents/review_list.html', context)


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
    
    return render(request, 'documents/review_form.html', context)


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
    
    return render(request, 'documents/review_detail.html', context)


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
    
    return render(request, 'documents/approval_form.html', context)


# ============================================================================
# DISTRIBUTION VIEWS
# ============================================================================

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
    
    return render(request, 'documents/distribution_form.html', context)


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
    
    return render(request, 'documents/acknowledgment_form.html', context)


# ============================================================================
# TRAINING VIEWS
# ============================================================================

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
    
    return render(request, 'documents/training_list.html', context)


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
    
    return render(request, 'documents/training_form.html', context)


# ============================================================================
# REFERENCE VIEWS
# ============================================================================

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
    
    return render(request, 'documents/reference_form.html', context)


# ============================================================================
# REPORTS & ANALYTICS
# ============================================================================

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
    
    return render(request, 'documents/reports.html', context)














# from django.shortcuts import render, get_object_or_404, redirect
# from django.contrib.auth.decorators import login_required, permission_required
# from django.contrib import messages
# from django.urls import reverse
# from django.db import transaction
# from .models import DocumentCategory, Document, DocumentVersion, ElectronicSignature, DocumentAuditTrail, DocumentTrainingRecord
# from .forms import DocumentCategoryForm, DocumentForm, DocumentVersionUploadForm, ElectronicSignatureForm
# from .utils import compute_sha256, create_verification_hash
# from django.utils import timezone


# # document_control/views.py (ADD THIS FUNCTION)


# @login_required
# def dashboard_view(request):
#     """
#     Dashboard showing the user's compliance action items and system status,
#     filtered strictly by the current tenant (request.user.tenant).
#     """
#     tenant = request.user.vendor
#     user = request.user
    
#     # 1. Action Item: Pending Approvals (21 CFR Part 11 & Workflow)
#     pending_approvals = DocumentVersion.objects.filter(
#         tenant=tenant,
#         status='REVIEW',
#         document__owner=user # Simplified rule: only the Document Owner can approve
#     ).select_related('document').order_by('document__title')


#     # 2. Action Item: Required Training (ISO 17025 Clause 6.2)
#     # Find all APPROVED, EFFECTIVE documents that the user has NOT acknowledged.
    
#     # Step 1: Get the PKs of versions the user HAS acknowledged.
#     acknowledged_versions_pks = DocumentTrainingRecord.objects.filter(
#         tenant=tenant,
#         user=user
#     ).values_list('document_version__pk', flat=True)
    
#     # Step 2: Get all APPROVED, EFFECTIVE versions, EXCLUDING those acknowledged PKs.
#     required_training_versions = DocumentVersion.objects.filter(
#         tenant=tenant,
#         status='APPROVED',
#         is_effective=True
#     ).exclude(
#         pk__in=acknowledged_versions_pks
#     ).select_related('document').order_by('document__title')


#     # 3. Action Item: My Active Drafts (Workflow)
#     # Drafts that the user started and are actively being worked on.
#     my_active_drafts = DocumentVersion.objects.filter(
#         tenant=tenant,
#         status='DRAFT',
#         created_by=user,
#         is_latest_draft=True
#     ).select_related('document').order_by('-created_at')


#     # 4. Status Check: Documents Due for Review (ISO 17025)
#     # Documents whose review due date is approaching (e.g., within the next 30 days).
#     future_date = timezone.now().date() + timezone.timedelta(days=30)
    
#     documents_due_soon = Document.objects.filter(
#         tenant=tenant,
#         review_due_date__gte=timezone.now().date(),
#         review_due_date__lte=future_date,
#         status='ACTIVE'
#     ).order_by('review_due_date')


#     context = {
#         'pending_approvals': pending_approvals,
#         'required_training': required_training_versions,
#         'my_active_drafts': my_active_drafts,
#         'documents_due_soon': documents_due_soon,
#     }
    
#     # Renders the main dashboard template
#     return render(request, 'doc_control/dashboard.html', context)


# # ----------------- Category CRUD -----------------
# @login_required
# def category_list(request):
#     categories = DocumentCategory.objects.filter(tenant=request.user.vendor)
#     return render(request, 'doc_control/category/list.html', {'categories': categories})


# @login_required
# def category_create(request):
#     if request.method == 'POST':
#         form = DocumentCategoryForm(request.POST)
#         if form.is_valid():
#             cat = form.save(commit=False)
#             cat.tenant = request.user.vendor  # assign tenant here
#             cat.created_by = request.user
#             cat.updated_by = request.user
#             cat.save()
#             messages.success(request, 'Category created')
#             return redirect('doc_control:category_list')
#     else:
#         form = DocumentCategoryForm()
#     return render(request, 'doc_control/category/form.html', {'form': form})



# @login_required
# def category_edit(request, pk):
#     cat = get_object_or_404(DocumentCategory, pk=pk, tenant=request.user.vendor)
#     if request.method == 'POST':
#         form = DocumentCategoryForm(request.POST, instance=cat)
#         if form.is_valid():
#             cat = form.save(commit=False)
#             cat.updated_by = request.user
#             cat.save()
#             messages.success(request, 'Category updated')
#             return redirect('doc_control:category_list')
#     else:
#         form = DocumentCategoryForm(instance=cat)
#     return render(request, 'doc_control/category/form.html', {'form': form})


# @login_required
# def category_delete(request, pk):
#     cat = get_object_or_404(DocumentCategory, pk=pk, tenant=request.user.vendor)
#     # Soft-delete pattern: mark inactive or disallow if referenced
#     if Document.objects.filter(category=cat).exists():
#         messages.error(request, 'Category is in use and cannot be deleted')
#         return redirect('doc_control:category_list')
#     cat.delete()
#     messages.success(request, 'Category deleted')
#     return redirect('doc_control:category_list')


# # ----------------- Document CRUD -----------------
# @login_required
# def document_list(request):
#     docs = Document.objects.filter(tenant=request.user.vendor)
#     return render(request, 'doc_control/document/list.html', {'documents': docs})


# @login_required
# def document_create(request):
#     if request.method == 'POST':
#         form = DocumentForm(request.POST)
#         if form.is_valid():
#             doc = form.save(commit=False)
#             doc.created_by = request.user
#             doc.updated_by = request.user
#             doc.tenant = request.user.tenant
#             doc.save()
#             messages.success(request, 'Document created')
#             return redirect('doc_control:document_list')
#     else:
#         form = DocumentForm(initial={'tenant': request.user.vendor})
#     return render(request, 'doc_control/document/form.html', {'form': form})


# @login_required
# def document_edit(request, pk):
#     doc = get_object_or_404(Document, pk=pk, tenant=request.user.vendor)
#     if request.method == 'POST':
#         form = DocumentForm(request.POST, instance=doc)
#         if form.is_valid():
#             doc = form.save(commit=False)
#             doc.updated_by = request.user
#             doc.save()
#             messages.success(request, 'Document updated')
#             return redirect('doc_control:document_list')
#     else:
#         form = DocumentForm(instance=doc)
#     return render(request, 'doc_control/document/form.html', {'form': form})


# @login_required
# def document_detail(request, pk):
#     """Shows the Document container and lists all its versions."""
#     doc = get_object_or_404(Document, pk=pk, tenant=request.user.vendor)
#     # Get all versions, ordered newest first
#     versions = doc.versions.all().order_by('-version_number') 
#     return render(request, 'doc_control/document/detail.html', {'document': doc, 'versions': versions})


# from django.http import JsonResponse
# # from django.views.decorators.http import require_POST
# # from django.core.exceptions import PermissionDenied

# @login_required
# def document_delete(request, pk):
#     """
#     Handles the compliant retirement (deactivation) of a Document via AJAX POST request.
#     Returns JSON response for client-side feedback.
#     """
#     tenant = request.user.tenant
#     user = request.user
    
#     try:
#         doc = get_object_or_404(Document, pk=pk, tenant=tenant)
#     except AttributeError:
#         # If the user object lacks a tenant attribute, deny access
#         return JsonResponse({'status': 'error', 'message': 'Tenant access is undefined.'}, status=403)
    
#     try:
#         with transaction.atomic():        
#             # --- Compliance Step 1: Deactivate the Document Container ---
#             doc.status = 'INACTIVE'
#             doc.updated_by = user
#             doc.save()

#             # --- Compliance Step 2: Clear the current_version pointer ---
#             if doc.current_version:
#                  # Mark the current effective version as obsolete/superseded
#                  doc.current_version.is_effective = False
#                  doc.current_version.is_obsolete = True
#                  doc.current_version.save()

#             # Remove pointer from the logical container
#             doc.current_version = None
#             doc.save()

#             # --- Compliance Step 3: Audit Trail ---
#             # Attempt to link the audit trail to the latest version for context
#             latest_version = doc.versions.order_by('-created_at').first()
#             if latest_version:
#                  version_context = {'version_pk': str(latest_version.pk)}
#             else:
#                  version_context = {'note': 'No previous versions found.'}

#             DocumentAuditTrail.objects.create(
#                 tenant=tenant,
#                 document_version=latest_version, 
#                 action='DOCUMENT.RETIRED',
#                 details={'document_title': doc.title, **version_context},
#                 performed_by=user,
#             )
            
#             return JsonResponse({
#                 'status': 'success',
#                 'message': f"Document '{doc.title}' has been successfully retired.",
#                 'doc_id': pk
#             })

#     except Exception as e:
#         # Log the exception for debugging
#         print(f"Error during document retirement: {e}") 
#         return JsonResponse({'status': 'error', 'message': 'An internal error occurred during retirement.'}, status=500)



# # @login_required
# # def document_delete(request, pk):
# #     """
# #     Deactivates a Document (Container) to comply with regulatory requirements, 
# #     preventing hard deletion of regulated data (DocumentVersions, Audits).
# #     """
# #     try:
# #         doc = get_object_or_404(Document, pk=pk, tenant=request.user.vendor)
# #     except AttributeError:
# #         # Handle case where request.user might not have a 'tenant' attribute
# #         messages.error(request, "Tenant access is undefined. Cannot perform operation.")
# #         return redirect('doc_control:document_list')

# #     # Security Check: Ensure the user has permission beyond standard login (e.g., 'can_retire_documents')
# #     # if not request.user.has_perm('doc_control.can_retire_documents'):
# #     #     messages.error(request, "You do not have permission to retire documents.")
# #     #     return redirect('doc_control:document_list')

# #     if request.method == 'POST':
# #         # FIX 2: Use a database transaction to ensure all related updates succeed or fail together
# #         with transaction.atomic():
# #             doc.status = 'INACTIVE'
# #             doc.updated_by = request.user
# #             doc.save()

# #             # --- Compliance Step 2: Clear the current_version pointer ---
# #             if doc.current_version:
# #                  doc.current_version.is_effective = False
# #                  doc.current_version.is_obsolete = True
# #                  doc.current_version.save()

# #             doc.current_version = None
# #             doc.save()

# #             # --- Compliance Step 3: Audit Trail ---
# #             DocumentAuditTrail.objects.create(
# #                 tenant=request.user.tenant,
# #                 document_version=doc.versions.order_by('-created_at').first(), # Link to the latest version for context
# #                 action='DOCUMENT.RETIRED',
# #                 details={'document_title': doc.title, 'reason': 'Document container deactivated by user.'},
# #                 performed_by=request.user,
# #             )
            
# #             messages.success(request, f"Document '{doc.title}' and its effective version have been safely retired.")
# #             return redirect('doc_control:document_list')
    

# #     # If not POST, render a confirmation template
# #     return render(request, 'doc_control/document/delete_confirm.html', {'document': doc})


# # ----------------- Document Version Workflow -----------------
# @login_required
# def version_upload(request, doc_id):
#     document = get_object_or_404(Document, pk=doc_id, tenant=request.user.tenant)
    
#     # Pre-Check: Only one DRAFT should exist at a time (Workflow Enforcement)
#     if document.versions.filter(status='DRAFT', is_obsolete=False).exists():
#         messages.error(request, 'A current draft already exists. Please review, approve, or reject it before uploading a new version.')
#         return redirect('doc_control:document_detail', pk=document.pk)

#     if request.method == 'POST':
#         form = DocumentVersionUploadForm(request.POST, request.FILES)
#         if form.is_valid():
#             with transaction.atomic():
#                 ver = form.save(commit=False)
#                 ver.tenant = request.user.tenant
#                 ver.document = document # Link to the parent Document
#                 ver.created_by = request.user
#                 ver.status = 'DRAFT'
#                 ver.is_latest_draft = True # Set the new version as the active draft
                
#                 # --- Compliance Step 1: File Checksum (Integrity) ---
#                 file_obj = request.FILES['file']
#                 ver.file_checksum = compute_sha256(file_obj) 
                
#                 # --- Compliance Step 2: Version Number Calculation (Traceability) ---
#                 latest_ver = document.versions.filter(is_obsolete=False).order_by('-created_at').first()
#                 if latest_ver and latest_ver.status == 'APPROVED':
#                     # Major version increment (e.g., 1.0 -> 2.0)
#                     base_version = int(float(latest_ver.version_number))
#                     ver.version_number = f"{base_version + 1}.0"
#                 elif latest_ver:
#                     # Minor version increment (e.g., 0.1 -> 0.2, if DRAFTs are tracked)
#                     ver.version_number = f"0.{document.versions.count() + 1}"
#                 else:
#                     ver.version_number = '1.0'

#                 ver.save()
                
#                 # --- Compliance Step 3: Audit Trail (Traceability) ---
#                 DocumentAuditTrail.objects.create(
#                     tenant=request.user.tenant,
#                     document_version=ver,
#                     action='VERSION.UPLOAD',
#                     details={'checksum': ver.file_checksum, 'filename': ver.file.name, 'version_num': ver.version_number},
#                     performed_by=request.user,
#                 )
#                 messages.success(request, f'Draft version {ver.version_number} uploaded.')
#             return redirect('doc_control:document_detail', pk=document.pk)
#     else:
#         # Pre-filter Category/Document in the form, if needed
#         form = DocumentVersionUploadForm()
#     return render(request, 'doc_control/version/upload.html', {'form': form, 'document': document})


# @login_required
# def version_detail(request, pk):
#     ver = get_object_or_404(DocumentVersion, pk=pk, tenant=request.user.tenant)
#     return render(request, 'doc_control/version/detail.html', {'version': ver})


# @login_required
# def start_review(request, pk):
#     ver = get_object_or_404(DocumentVersion, pk=pk, tenant=request.user.tenant)
#     # mark in review and create audit
#     ver.status = 'REVIEW'
#     ver.save()
#     DocumentAuditTrail.objects.create(tenant=request.user.tenant, document_version=ver, action='VERSION.REVIEW.START', details={}, performed_by=request.user)
#     messages.success(request, 'Review started')
#     return redirect('doc_control:version_detail', pk=ver.pk)


# @login_required
# def approve_version(request, pk):
#     ver = get_object_or_404(DocumentVersion, pk=pk, tenant=request.user.tenant, status='REVIEW')

#     # Security: Only Document Owner or authorized role should approve
#     if ver.document.owner != request.user and not request.user.has_perm('doc_control.can_approve_documents'):
#         messages.error(request, "You do not have permission to approve this document.")
#         return redirect('doc_control:version_detail', pk=ver.pk)

#     if request.method == 'POST':
#         form = ElectronicSignatureForm(request.user, request.POST)
#         if form.is_valid():
#             reason = form.cleaned_data['reason']
            
#             # --- Compliance Step 1: Get Password Verification Data ---
#             # The form.is_valid() call authenticated the user's password.
#             # We use the user's current hashed password from the DB as part of the unique link.
#             password_hash = request.user.password 
#             timestamp_iso = timezone.now().isoformat()
            
#             # --- Compliance Step 2: Create Verification Hash (21 CFR 11 Link) ---
#             sig_value = create_verification_hash(request.user.id, password_hash, timestamp_iso)

#             with transaction.atomic():
#                 # 1. Create the Immutable Electronic Signature Record
#                 sig = ElectronicSignature.objects.create(
#                     tenant=request.user.tenant,
#                     user=request.user,
#                     document_version=ver,
#                     action='APPROVAL',
#                     verification_data=sig_value, # The non-repudiable hash
#                     reason=reason,
#                     created_by=request.user
#                 )
                
#                 # 2. Update the Version status (ISO 17025)
#                 # This function handles setting status='APPROVED' and is_effective=True
#                 ver.approve(request.user) 
                
#                 # 3. Supersede old versions and update the Document pointer
#                 DocumentVersion.objects.filter(document=ver.document, is_effective=True, is_obsolete=False).exclude(pk=ver.pk).update(is_effective=False, is_obsolete=True)
#                 ver.document.current_version = ver
#                 ver.document.updated_by = request.user
#                 ver.document.save()
                
#                 # 4. Audit Trail
#                 DocumentAuditTrail.objects.create(
#                     tenant=request.user.tenant, 
#                     document_version=ver, 
#                     action='VERSION.APPROVE', 
#                     details={'signature_id': str(sig.id), 'sig_reason': reason}, 
#                     performed_by=request.user
#                 )
                
#             messages.success(request, f'Version {ver.version_number} approved and released.')
#             return redirect('doc_control:version_detail', pk=ver.pk)
#     else:
#         form = ElectronicSignatureForm(request.user)
#     return render(request, 'doc_control/approval/version.html', {'form': form, 'version': ver})


# # ----------------- Training Acknowledgement -----------------
# @login_required
# def acknowledge_training(request, pk):
#     ver = get_object_or_404(DocumentVersion, pk=pk, tenant=request.user.tenant, status='APPROVED')
#     # create training record if not exists
#     tr, created = DocumentTrainingRecord.objects.get_or_create(tenant=request.user.tenant, user=request.user, document_version=ver, created_by=request.user)
#     if created:
#         DocumentAuditTrail.objects.create(tenant=request.user.tenant, document_version=ver, action='TRAINING.ACK', details={}, performed_by=request.user)
#         messages.success(request, 'Acknowledgement recorded')
#     else:
#         messages.info(request, 'Already acknowledged')
#     return redirect('doc_control:version_detail', pk=ver.pk)



# # @login_required
# # def approve_version(request, pk):
# #     ver = get_object_or_404(DocumentVersion, pk=pk, tenant=request.user.tenant)
# #     if request.method == 'POST':
# #         form = ElectronicSignatureForm(request.user, request.POST)
# #         if form.is_valid():
# #             reason = form.cleaned_data['reason']
# #             # create signature
# #             sig_value = sign_electronic_signature(request.user, ver, reason)
# #             with transaction.atomic():
# #                 sig = ElectronicSignature.objects.create(
# #                     tenant=request.user.tenant,
# #                     user=request.user,
# #                     document_version=ver,
# #                     action='APPROVAL',
# #                     verification_data=sig_value,
# #                     reason=reason,
# #                     created_by=request.user
# #                 )
# #                 ver.approve(request.user)
# #                 # set document's current_version pointer
# #                 ver.document.current_version = ver
# #                 ver.document.updated_by = request.user
# #                 ver.document.save()
# #                 # audit
# #                 DocumentAuditTrail.objects.create(tenant=request.user.tenant, document_version=ver, action='VERSION.APPROVE', details={'signature_id': str(sig.id)}, performed_by=request.user)
# #             messages.success(request, 'Version approved and released')
# #             return redirect('doc_control:version_detail', pk=ver.pk)
# #     else:
# #         form = ElectronicSignatureForm(request.user)
# #     return render(request, 'doc_control/approval/version.html', {'form': form, 'version': ver})

