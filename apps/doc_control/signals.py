from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.utils import timezone
from .models import (
    ControlledDocument, DocumentVersion, DocumentReview,
    DocumentApproval, DocumentDistribution, DocumentTraining,
    DocumentAuditLog
)


@receiver(post_save, sender=ControlledDocument)
def document_post_save(sender, instance, created, **kwargs):
    """
    Create audit log when document is created or updated
    Note: This is a basic implementation. In views, we have more detailed audit logging
    with request context (IP address, user agent).
    """
    if created:
        # Document was just created
        action = 'created'
        description = f'Document {instance.document_number} created'
    else:
        # Document was updated
        action = 'updated'
        description = f'Document {instance.document_number} updated'
    
    # Only create audit log if we have the necessary information
    if instance.vendor and instance.updated_by:
        DocumentAuditLog.objects.create(
            vendor=instance.vendor,
            document=instance,
            action=action,
            user=instance.updated_by,
            user_full_name=instance.updated_by.get_full_name() or instance.updated_by.username,
            description=description,
            ip_address='127.0.0.1',  # Default, should be overridden in views
            timestamp=timezone.now()
        )


@receiver(post_save, sender=DocumentVersion)
def document_version_created(sender, instance, created, **kwargs):
    """Create audit log when new version is created"""
    if created and instance.document:
        DocumentAuditLog.objects.create(
            vendor=instance.vendor,
            document=instance.document,
            action='updated',
            user=instance.created_by,
            user_full_name=instance.created_by.get_full_name() if instance.created_by else 'System',
            description=f'New version {instance.version_number} created: {instance.change_description[:100]}',
            ip_address='127.0.0.1',
            timestamp=timezone.now()
        )


@receiver(post_save, sender=DocumentApproval)
def document_approval_created(sender, instance, created, **kwargs):
    """Create audit log when document is approved/rejected"""
    if created:
        action = 'approved' if instance.approval_status == 'approved' else 'rejected'
        description = f'Document {action} by {instance.approver.get_full_name() or instance.approver.username}'
        
        DocumentAuditLog.objects.create(
            vendor=instance.vendor,
            document=instance.document,
            action=action,
            user=instance.approver,
            user_full_name=instance.approver.get_full_name() or instance.approver.username,
            description=description,
            ip_address=instance.ip_address,
            user_agent=instance.user_agent,
            timestamp=instance.signed_at
        )
        
        # Update document status if approved
        if instance.approval_status == 'approved' and instance.approval_type == 'approver':
            # Only update to approved if it's the final approver
            if instance.document.status in ['draft', 'under_review']:
                instance.document.status = 'approved'
                instance.document.save()


@receiver(post_save, sender=DocumentDistribution)
def document_distribution_created(sender, instance, created, **kwargs):
    """Create audit log when document is distributed"""
    if created:
        DocumentAuditLog.objects.create(
            vendor=instance.vendor,
            document=instance.document,
            action='distributed',
            user=instance.distributed_by,
            user_full_name=instance.distributed_by.get_full_name() if instance.distributed_by else 'System',
            description=f'Document distributed to {instance.distributed_to.get_full_name() or instance.distributed_to.username}',
            ip_address='127.0.0.1',
            timestamp=instance.distributed_at
        )


@receiver(post_save, sender=DocumentDistribution)
def document_acknowledged(sender, instance, created, **kwargs):
    """Create audit log when document is acknowledged"""
    if not created and instance.acknowledged and instance.acknowledged_at:
        # Check if this is a new acknowledgment
        try:
            old_instance = DocumentDistribution.objects.get(pk=instance.pk)
            if not old_instance.acknowledged:  # This is a new acknowledgment
                DocumentAuditLog.objects.create(
                    vendor=instance.vendor,
                    document=instance.document,
                    action='viewed',  # Using 'viewed' action for acknowledgment
                    user=instance.distributed_to,
                    user_full_name=instance.distributed_to.get_full_name() or instance.distributed_to.username,
                    description=f'Document acknowledged by {instance.distributed_to.get_full_name() or instance.distributed_to.username}',
                    ip_address='127.0.0.1',
                    timestamp=instance.acknowledged_at
                )
        except DocumentDistribution.DoesNotExist:
            pass


@receiver(post_save, sender=DocumentTraining)
def training_assigned(sender, instance, created, **kwargs):
    """Create notification when training is assigned"""
    if created:
        # You can add email notification here
        pass


@receiver(pre_save, sender=ControlledDocument)
def document_status_change(sender, instance, **kwargs):
    """Track status changes"""
    if instance.pk:
        try:
            old_instance = ControlledDocument.objects.get(pk=instance.pk)
            if old_instance.status != instance.status:
                # Status changed - this will be logged in post_save
                if instance.status == 'obsolete':
                    # Mark as obsolete
                    instance.obsolete_date = timezone.now().date()
        except ControlledDocument.DoesNotExist:
            pass


@receiver(post_delete, sender=ControlledDocument)
def document_deleted(sender, instance, **kwargs):
    """Create audit log when document is deleted (if soft delete is not used)"""
    # Note: In production, you might want to use soft delete instead of hard delete
    # This is just for tracking if hard delete is used
    if instance.vendor:
        DocumentAuditLog.objects.create(
            vendor=instance.vendor,
            document=None,  # Document is deleted
            action='retired',
            user=None,
            user_full_name='System',
            description=f'Document {instance.document_number} was deleted',
            ip_address='127.0.0.1',
            timestamp=timezone.now()
        )


# Automatic review scheduling
@receiver(post_save, sender=ControlledDocument)
def schedule_periodic_review(sender, instance, created, **kwargs):
    """
    Automatically schedule periodic review when document becomes effective
    """
    if instance.status == 'effective' and not instance.next_review_date:
        if instance.effective_date and instance.review_frequency_days:
            instance.next_review_date = instance.calculate_next_review_date()
            # Use update to avoid triggering another post_save
            ControlledDocument.objects.filter(pk=instance.pk).update(
                next_review_date=instance.next_review_date
            )


# Document version synchronization
@receiver(post_save, sender=DocumentVersion)
def sync_document_version(sender, instance, created, **kwargs):
    """
    Update main document's version number when new version is created
    """
    if created:
        # Update the main document's current version
        ControlledDocument.objects.filter(pk=instance.document.pk).update(
            version=instance.version_number
        )


# Training completion tracking
@receiver(post_save, sender=DocumentTraining)
def training_completed(sender, instance, created, **kwargs):
    """
    Track training completion and update related records
    """
    if not created and instance.status == 'completed' and instance.completed_at:
        # You can add logic here to:
        # 1. Send completion notification
        # 2. Update user's training matrix
        # 3. Generate certificate
        pass


# Review workflow automation
@receiver(post_save, sender=DocumentReview)
def review_status_change(sender, instance, created, **kwargs):
    """
    Automate document status based on review completion
    """
    if not created:
        if instance.status == 'approved':
            # Review approved - update document status
            if instance.document.status == 'under_review':
                instance.document.status = 'approved'
                instance.document.save()
        elif instance.status == 'rejected':
            # Review rejected - send back to draft
            if instance.document.status == 'under_review':
                instance.document.status = 'draft'
                instance.document.save()


# Supersession handling
@receiver(post_save, sender=ControlledDocument)
def handle_supersession(sender, instance, created, **kwargs):
    """
    When a document becomes effective and supersedes another document,
    automatically obsolete the old document
    """
    if instance.status == 'effective' and instance.supersedes:
        if instance.supersedes.status == 'effective':
            # Mark superseded document as obsolete
            ControlledDocument.objects.filter(pk=instance.supersedes.pk).update(
                status='obsolete'
            )


# File integrity check
@receiver(pre_save, sender=ControlledDocument)
def verify_file_integrity(sender, instance, **kwargs):
    """
    Verify file hasn't been tampered with by checking checksum
    """
    if instance.pk and instance.file:
        try:
            old_instance = ControlledDocument.objects.get(pk=instance.pk)
            if old_instance.file and old_instance.file != instance.file:
                # File changed - recalculate checksum (done in form save)
                pass
        except ControlledDocument.DoesNotExist:
            pass


# Notification triggers (placeholder for email/notification system)
@receiver(post_save, sender=DocumentReview)
def send_review_notification(sender, instance, created, **kwargs):
    """
    Send notification to reviewer when review is assigned
    """
    if created:
        # TODO: Implement email notification
        # send_mail(
        #     subject=f'Document Review Assigned: {instance.document.document_number}',
        #     message=f'You have been assigned to review {instance.document.title}',
        #     recipient_list=[instance.reviewer.email]
        # )
        pass


@receiver(post_save, sender=DocumentDistribution)
def send_distribution_notification(sender, instance, created, **kwargs):
    """
    Send notification when document is distributed
    """
    if created:
        # TODO: Implement email notification
        # send_mail(
        #     subject=f'New Document: {instance.document.document_number}',
        #     message=f'A new document has been distributed to you: {instance.document.title}',
        #     recipient_list=[instance.distributed_to.email]
        # )
        pass