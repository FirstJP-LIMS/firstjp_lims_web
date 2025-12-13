from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone
import hashlib
from .models import (
    DocumentCategory, ControlledDocument, DocumentVersion,
    DocumentReview, DocumentApproval, DocumentDistribution,
    DocumentTraining, DocumentReference
)

User = get_user_model()


class DocumentCategoryForm(forms.ModelForm):
    """Form for creating/editing document categories"""
    
    class Meta:
        model = DocumentCategory
        fields = [
            'name', 'code', 'description', 'requires_training',
            'retention_period_days', 'is_active'
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Standard Operating Procedure'
            }),
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., SOP'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Describe this category...'
            }),
            'retention_period_days': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1'
            }),
            'requires_training': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        self.vendor = kwargs.pop('vendor', None)
        super().__init__(*args, **kwargs)
    
    def clean_code(self):
        code = self.cleaned_data.get('code', '').upper()
        
        # Check for duplicate code within the same vendor
        if self.vendor:
            existing = DocumentCategory.objects.filter(
                vendor=self.vendor,
                code=code
            ).exclude(pk=self.instance.pk if self.instance else None)
            
            if existing.exists():
                raise ValidationError(f"Category code '{code}' already exists for your organization.")
        
        return code


class ControlledDocumentForm(forms.ModelForm):
    """Form for creating/editing controlled documents"""
    
    class Meta:
        model = ControlledDocument
        fields = [
            'category', 'document_number', 'title', 'version',
            'description', 'purpose', 'scope', 'file',
            'status', 'effective_date', 'expiry_date',
            'review_frequency_days', 'owner', 'department',
            'requires_electronic_signature', 'requires_training',
            'is_controlled', 'supersedes', 'keywords'
        ]
        widgets = {
            'category': forms.Select(attrs={'class': 'form-control'}),
            'document_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., SOP-QC-001'
            }),
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Document title'
            }),
            'version': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '1.0'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3
            }),
            'purpose': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3
            }),
            'scope': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3
            }),
            'file': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': '.pdf,.docx,.xlsx,.txt'
            }),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'effective_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'expiry_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'review_frequency_days': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1'
            }),
            'owner': forms.Select(attrs={'class': 'form-control'}),
            'department': forms.TextInput(attrs={
                'class': 'form-control'
            }),
            'supersedes': forms.Select(attrs={'class': 'form-control'}),
            'keywords': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Comma-separated keywords'
            }),
            'requires_electronic_signature': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'requires_training': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'is_controlled': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        self.vendor = kwargs.pop('vendor', None)
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Filter choices by vendor
        if self.vendor:
            self.fields['category'].queryset = DocumentCategory.objects.filter(
                vendor=self.vendor,
                is_active=True
            )
            self.fields['owner'].queryset = User.objects.filter(
                vendor=self.vendor,
                is_active=True
            )
            self.fields['supersedes'].queryset = ControlledDocument.objects.filter(
                vendor=self.vendor,
                status__in=['effective', 'obsolete']
            ).exclude(pk=self.instance.pk if self.instance else None)
    
    def clean_document_number(self):
        doc_number = self.cleaned_data.get('document_number', '').upper()
        version = self.cleaned_data.get('version', '1.0')
        
        # Check for duplicate document_number + version
        if self.vendor:
            existing = ControlledDocument.objects.filter(
                vendor=self.vendor,
                document_number=doc_number,
                version=version
            ).exclude(pk=self.instance.pk if self.instance else None)
            
            if existing.exists():
                raise ValidationError(
                    f"Document '{doc_number}' version '{version}' already exists."
                )
        
        return doc_number
    
    def clean(self):
        cleaned_data = super().clean()
        effective_date = cleaned_data.get('effective_date')
        expiry_date = cleaned_data.get('expiry_date')
        
        # Validate date logic
        if effective_date and expiry_date:
            if expiry_date <= effective_date:
                raise ValidationError({
                    'expiry_date': 'Expiry date must be after effective date.'
                })
        
        return cleaned_data
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        
        # Calculate file checksum if file is uploaded
        if instance.file:
            instance.file_size = instance.file.size
            
            # Calculate SHA-256 checksum
            sha256_hash = hashlib.sha256()
            for chunk in instance.file.chunks():
                sha256_hash.update(chunk)
            instance.checksum = sha256_hash.hexdigest()
        
        # Calculate next review date
        if instance.effective_date and instance.review_frequency_days:
            instance.next_review_date = instance.calculate_next_review_date()
        
        if commit:
            instance.save()
        
        return instance


class DocumentVersionForm(forms.ModelForm):
    """Form for creating new document versions"""
    
    class Meta:
        model = DocumentVersion
        fields = [
            'version_number', 'change_description', 'change_type',
            'file', 'effective_date'
        ]
        widgets = {
            'version_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., 2.0'
            }),
            'change_description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Describe changes in this version...'
            }),
            'change_type': forms.Select(attrs={'class': 'form-control'}),
            'file': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': '.pdf,.docx,.xlsx,.txt'
            }),
            'effective_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        self.document = kwargs.pop('document', None)
        self.vendor = kwargs.pop('vendor', None)
        super().__init__(*args, **kwargs)
        
        # Make file required
        self.fields['file'].required = True
    
    def clean_version_number(self):
        version = self.cleaned_data.get('version_number')
        
        if self.document:
            existing = DocumentVersion.objects.filter(
                document=self.document,
                version_number=version
            ).exclude(pk=self.instance.pk if self.instance else None)
            
            if existing.exists():
                raise ValidationError(
                    f"Version '{version}' already exists for this document."
                )
        
        return version
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        
        # Set document and vendor
        if self.document:
            instance.document = self.document
        if self.vendor:
            instance.vendor = self.vendor
        
        # Calculate file size and checksum
        if instance.file:
            instance.file_size = instance.file.size
            
            sha256_hash = hashlib.sha256()
            for chunk in instance.file.chunks():
                sha256_hash.update(chunk)
            instance.checksum = sha256_hash.hexdigest()
        
        if commit:
            instance.save()
        
        return instance


class DocumentReviewForm(forms.ModelForm):
    """Form for creating/updating document reviews"""
    
    class Meta:
        model = DocumentReview
        fields = [
            'document', 'review_type', 'status', 'reviewer',
            'approver', 'due_date', 'comments', 'recommendations'
        ]
        widgets = {
            'document': forms.Select(attrs={'class': 'form-control'}),
            'review_type': forms.Select(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'reviewer': forms.Select(attrs={'class': 'form-control'}),
            'approver': forms.Select(attrs={'class': 'form-control'}),
            'due_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'comments': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4
            }),
            'recommendations': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4
            }),
        }
    
    def __init__(self, *args, **kwargs):
        self.vendor = kwargs.pop('vendor', None)
        super().__init__(*args, **kwargs)
        
        if self.vendor:
            self.fields['document'].queryset = ControlledDocument.objects.filter(
                vendor=self.vendor,
                is_active=True
            )
            self.fields['reviewer'].queryset = User.objects.filter(
                vendor=self.vendor,
                is_active=True
            )
            self.fields['approver'].queryset = User.objects.filter(
                vendor=self.vendor,
                is_active=True
            )


class DocumentApprovalForm(forms.ModelForm):
    """Form for electronic signature and approval"""
    
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your password to sign'
        }),
        help_text='Enter your password to electronically sign this document'
    )
    
    class Meta:
        model = DocumentApproval
        fields = [
            'approval_type', 'approval_status',
            'reason_for_signature', 'comments'
        ]
        widgets = {
            'approval_type': forms.Select(attrs={'class': 'form-control'}),
            'approval_status': forms.Select(attrs={'class': 'form-control'}),
            'reason_for_signature': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Approved for implementation'
            }),
            'comments': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3
            }),
        }
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
    
    def clean_password(self):
        password = self.cleaned_data.get('password')
        
        if self.user and not self.user.check_password(password):
            raise ValidationError('Invalid password. Please try again.')
        
        return password
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        
        # Set approver
        if self.user:
            instance.approver = self.user
            
            # Create encrypted signature (username + timestamp + hash)
            signature_string = f"{self.user.username}_{timezone.now().isoformat()}"
            instance.signature = hashlib.sha256(
                signature_string.encode()
            ).hexdigest()
        
        # Capture IP address and user agent
        if self.request:
            x_forwarded_for = self.request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                instance.ip_address = x_forwarded_for.split(',')[0]
            else:
                instance.ip_address = self.request.META.get('REMOTE_ADDR', '0.0.0.0')
            
            instance.user_agent = self.request.META.get('HTTP_USER_AGENT', '')[:255]
        
        if commit:
            instance.save()
        
        return instance


class DocumentDistributionForm(forms.ModelForm):
    """Form for distributing documents to users"""
    
    users = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(),
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        required=True,
        help_text='Select users to distribute this document to'
    )
    
    class Meta:
        model = DocumentDistribution
        fields = ['distribution_method', 'requires_acknowledgment']
        widgets = {
            'distribution_method': forms.Select(attrs={'class': 'form-control'}),
            'requires_acknowledgment': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        self.vendor = kwargs.pop('vendor', None)
        self.document = kwargs.pop('document', None)
        super().__init__(*args, **kwargs)
        
        if self.vendor:
            self.fields['users'].queryset = User.objects.filter(
                vendor=self.vendor,
                is_active=True
            )


class DocumentTrainingForm(forms.ModelForm):
    """Form for assigning and recording training"""
    
    trainees = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(),
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        required=False,
        help_text='Select users who need training on this document'
    )
    
    class Meta:
        model = DocumentTraining
        fields = [
            'trainee', 'training_type', 'status', 'trainer',
            'training_duration_minutes', 'assessment_score',
            'assessment_passed', 'expiry_date', 'notes'
        ]
        widgets = {
            'trainee': forms.Select(attrs={'class': 'form-control'}),
            'training_type': forms.Select(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'trainer': forms.Select(attrs={'class': 'form-control'}),
            'training_duration_minutes': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1'
            }),
            'assessment_score': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'max': '100',
                'step': '0.01'
            }),
            'assessment_passed': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'expiry_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3
            }),
        }
    
    def __init__(self, *args, **kwargs):
        self.vendor = kwargs.pop('vendor', None)
        self.document = kwargs.pop('document', None)
        super().__init__(*args, **kwargs)
        
        if self.vendor:
            user_queryset = User.objects.filter(
                vendor=self.vendor,
                is_active=True
            )
            self.fields['trainee'].queryset = user_queryset
            self.fields['trainer'].queryset = user_queryset
            self.fields['trainees'].queryset = user_queryset


class DocumentAcknowledgmentForm(forms.Form):
    """Form for acknowledging document receipt"""
    
    acknowledgment_text = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'readonly': 'readonly'
        }),
        initial='I acknowledge that I have received and reviewed this document.',
        disabled=True
    )
    
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your password to acknowledge'
        }),
        help_text='Enter your password to electronically acknowledge'
    )
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
    
    def clean_password(self):
        password = self.cleaned_data.get('password')
        
        if self.user and not self.user.check_password(password):
            raise ValidationError('Invalid password. Please try again.')
        
        return password


class DocumentSearchForm(forms.Form):
    """Form for searching documents"""
    
    query = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Search by document number, title, or keywords...'
        })
    )
    
    category = forms.ModelChoiceField(
        queryset=DocumentCategory.objects.none(),
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'}),
        empty_label='All Categories'
    )
    
    status = forms.ChoiceField(
        choices=[('', 'All Statuses')] + ControlledDocument.STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    owner = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'}),
        empty_label='All Owners'
    )
    
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )
    
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )
    
    def __init__(self, *args, **kwargs):
        vendor = kwargs.pop('vendor', None)
        super().__init__(*args, **kwargs)
        
        if vendor:
            self.fields['category'].queryset = DocumentCategory.objects.filter(
                vendor=vendor,
                is_active=True
            )
            self.fields['owner'].queryset = User.objects.filter(
                vendor=vendor,
                is_active=True
            )


class DocumentReferenceForm(forms.ModelForm):
    """Form for creating document references"""
    
    class Meta:
        model = DocumentReference
        fields = ['referenced_document', 'reference_type', 'notes']
        widgets = {
            'referenced_document': forms.Select(attrs={'class': 'form-control'}),
            'reference_type': forms.Select(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3
            }),
        }
    
    def __init__(self, *args, **kwargs):
        self.vendor = kwargs.pop('vendor', None)
        self.source_document = kwargs.pop('source_document', None)
        super().__init__(*args, **kwargs)
        
        if self.vendor and self.source_document:
            # Exclude the source document itself
            self.fields['referenced_document'].queryset = ControlledDocument.objects.filter(
                vendor=self.vendor,
                is_active=True
            ).exclude(pk=self.source_document.pk)




# from django import forms
# from django.core.exceptions import ValidationError
# from django.contrib.auth import authenticate, get_user_model
# from .models import (DocumentCategory, Document, DocumentVersion, 
#                      ElectronicSignature, DocumentTrainingRecord)

# User = get_user_model()


# class DocumentCategoryForm(forms.ModelForm):
#     class Meta:
#         model = DocumentCategory
#         fields = ['name', 'description']
#         widgets = {
#             'name': forms.TextInput(attrs={
#                 'class': 'form-control',
#                 'placeholder': 'Enter category name',
#                 'autofocus': True
#             }),
#             'description': forms.Textarea(attrs={
#                 'class': 'form-control',
#                 'placeholder': 'Optional: Add a description for this category',
#                 'rows': 4
#             }),
#         }
    
#     def __init__(self, *args, **kwargs):
#         super().__init__(*args, **kwargs)
#         # Add required attribute for client-side validation
#         self.fields['name'].required = True
#         self.fields['name'].widget.attrs['required'] = 'required'

# # --- 2. Document Form (Administrative Container) ---

# class DocumentForm(forms.ModelForm):
#     owner = forms.ModelChoiceField(
#         queryset=User.objects.all(),
#         required=False,
#         label="Document Owner",
#         widget=forms.Select(attrs={
#             'class': 'form-select',
#             'placeholder': 'Select document owner'
#         })
#     )

#     class Meta:
#         model = Document
#         fields = ['title', 'category', 'effective_date', 'review_due_date', 'owner']
#         widgets = {
#             'title': forms.TextInput(attrs={
#                 'class': 'form-control',
#                 'placeholder': 'Enter document title',
#                 'autofocus': True
#             }),
#             'category': forms.Select(attrs={
#                 'class': 'form-select',
#                 'required': 'required'
#             }),
#             'effective_date': forms.DateInput(attrs={
#                 'type': 'date',
#                 'class': 'form-control'
#             }),
#             'review_due_date': forms.DateInput(attrs={
#                 'type': 'date',
#                 'class': 'form-control'
#             }),
#         }
    
#     def __init__(self, *args, **kwargs):
#         super().__init__(*args, **kwargs)
#         # Add required attribute for client-side validation
#         self.fields['title'].required = True
#         self.fields['title'].widget.attrs['required'] = 'required'
#         self.fields['category'].required = True
#         self.fields['category'].widget.attrs['required'] = 'required'
        
#         # Filter owner queryset by tenant if needed
#         if 'initial' in kwargs and 'tenant' in kwargs['initial']:
#             tenant = kwargs['initial']['tenant']
#             self.fields['owner'].queryset = User.objects.filter(vendor=tenant)


# # --- 3. Document Version Upload Form (File Artifact) ---
# class DocumentVersionUploadForm(forms.ModelForm):
#     # Only allow the user to select the file and describe the change.
#     file = forms.FileField(required=True)

#     class Meta:
#         model = DocumentVersion
#         fields = ['file', 'change_summary'] 

#     def clean_file(self):
#         # Enforce basic file security/type policy here
#         file = self.cleaned_data.get('file')
#         if file and not file.name.lower().endswith(('.pdf', '.docx', '.xlsx')):
#              raise ValidationError("Only PDF, DOCX, and XLSX files are supported for controlled documents.")
#         return file
    

# class ElectronicSignatureForm(forms.Form):
#     reason = forms.CharField(
#         max_length=255,
#         required=True,
#         widget=forms.Textarea(attrs={
#             'class': 'form-control',
#             'placeholder': 'Enter reason for approval...',
#             'rows': 3
#         })
#     )
#     password = forms.CharField(
#         widget=forms.PasswordInput(attrs={
#             'class': 'form-control',
#             'placeholder': 'Enter your password'
#         }),
#         required=True
#     )
    
#     def __init__(self, user, *args, **kwargs):
#         super().__init__(*args, **kwargs)
#         self.user = user
    
#     def clean(self):
#         cleaned_data = super().clean()
#         password = cleaned_data.get('password')
        
#         if password:
#             # Verify the password against the user's actual password
#             if not self.user.check_password(password):
#                 raise forms.ValidationError('Invalid password.')
        
#         return cleaned_data

# # --- 5. Document Training Acknowledge Form (ISO 17025) ---
# class DocumentTrainingAcknowledgeForm(forms.ModelForm):
#     """
#     Form for a user to formally acknowledge they have read/trained on a document.
#     Often, this is just a button on the UI, but using a form is safer.
#     """
#     class Meta:
#         model = DocumentTrainingRecord
#         # The only field needed is the version, but we set that in the view too.
#         fields = [] # Empty, as all data (user, version, timestamp) is set in the view




