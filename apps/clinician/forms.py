from django import forms
from django.db import transaction
from ..labs.models import TestRequest, VendorTest, Patient
from .models import ClinicianPatientRelationship

class ClinicianTestOrderForm(forms.ModelForm):
    """
    Form for clinicians to create test orders for patients.
    Simplified interface focused on clinical workflow.
    """
    
    # Patient selection
    patient_id = forms.CharField(required=False, max_length=20,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter Patient ID to search',
            'autocomplete': 'off',
        }),
        label="Patient ID"
    )
    
    # Test selection (will be populated via JavaScript or multi-select)
    requested_tests = forms.ModelMultipleChoiceField(
        queryset=VendorTest.objects.none(),
        required=True,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        label="Select Tests to Order"
    )
    
    class Meta:
        model = TestRequest
        fields = [
            'patient_id',
            'requested_tests',
            'clinical_indication',
            'clinical_history',
            'priority',
            'urgency_reason',
            'has_informed_consent',
            'external_referral',
        ]
        
        widgets = {
            'clinical_indication': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Clinical reason for ordering (diagnosis, symptoms, ICD codes)...',
                'required': True,
            }),
            'clinical_history': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Relevant medical history, current medications, allergies...'
            }),
            'priority': forms.Select(attrs={'class': 'form-select'}),
            'urgency_reason': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Required for urgent/STAT orders'
            }),
            'external_referral': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Referring physician/institution (if applicable)'
            }),
        }
    
    def __init__(self, *args, user=None, vendor=None, patient=None, **kwargs):
        """
        Initialize form with clinician context.
        
        Args:
            user: Current clinician user
            vendor: Current vendor
            patient: Pre-selected patient (optional)
        """
        super().__init__(*args, **kwargs)
        
        self.user = user
        self.vendor = vendor
        self.patient = patient
        
        # Configure test queryset - clinicians see all enabled tests
        if vendor:
            self.fields['requested_tests'].queryset = VendorTest.objects.filter(
                vendor=vendor,
                enabled=True
            ).select_related('assigned_department').order_by('name')
        
        # If patient pre-selected, hide patient_id field
        if patient:
            del self.fields['patient_id']
        else:
            self.fields['patient_id'].required = True
        
        # Make clinical indication required
        self.fields['clinical_indication'].required = True
        
        # Consent checkbox
        self.fields['has_informed_consent'].widget = forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        })
        self.fields['has_informed_consent'].label = "Patient has provided informed consent"
    
    def clean_patient_id(self):
        """Validate and retrieve patient."""
        patient_id = self.cleaned_data.get('patient_id')
        
        if not self.patient and patient_id:
            try:
                patient = Patient.objects.get(
                    patient_id=patient_id,
                    vendor=self.vendor
                )
                
                # Auto-create or verify clinician-patient relationship
                relationship, created = ClinicianPatientRelationship.objects.get_or_create(
                    clinician=self.user,
                    patient=patient,
                    defaults={
                        'relationship_type': 'consulting',
                        'established_via': 'Test order',
                        'is_active': True,
                    }
                )
                
                if not relationship.can_order_tests:
                    raise forms.ValidationError(
                        "You don't have permission to order tests for this patient."
                    )
                
                return patient
                
            except Patient.DoesNotExist:
                raise forms.ValidationError(
                    f"Patient with ID '{patient_id}' not found. Please verify the ID."
                )
        
        return patient_id
    
    def clean_requested_tests(self):
        """Validate test selection."""
        tests = self.cleaned_data.get('requested_tests')
        
        if not tests or tests.count() == 0:
            raise forms.ValidationError("Please select at least one test.")
        
        return tests
    
    def clean(self):
        cleaned = super().clean()
        
        # Validate urgency justification
        priority = cleaned.get('priority')
        urgency_reason = cleaned.get('urgency_reason')
        
        if priority == 'urgent' and not urgency_reason:
            self.add_error('urgency_reason', 'Justification required for urgent/STAT orders.')
        
        # Validate consent
        if not cleaned.get('has_informed_consent'):
            self.add_error('has_informed_consent', 'Patient consent is required to proceed.')
        
        return cleaned
    
    def save(self, commit=True):
        """Create test request with clinician attribution."""
        instance = super().save(commit=False)
        
        # Set vendor
        instance.vendor = self.vendor
        
        # Set patient
        patient = self.cleaned_data.get('patient_id') or self.patient
        instance.patient = patient
        
        # Set clinician attribution
        instance.requested_by = self.user
        instance.ordering_clinician = self.user
        
        if commit:
            with transaction.atomic():
                instance.save()
                
                # Add selected tests (M2M)
                instance.requested_tests.set(self.cleaned_data['requested_tests'])
                
                # Check if approval needed (for patient self-orders)
                # Clinician orders don't need approval
                instance.check_approval_requirement()
                
                # Update clinician statistics
                if hasattr(self.user, 'clinician_profile'):
                    self.user.clinician_profile.increment_order_count()
        
        return instance


class QuickTestOrderForm(forms.Form):
    """
    Use in detail page
    Simplified form for quick test ordering from patient detail page.
    """
    tests = forms.ModelMultipleChoiceField(
        queryset=VendorTest.objects.none(),
        required=True,
        widget=forms.CheckboxSelectMultiple,
        label="Select Tests"
    )
    
    clinical_indication = forms.CharField(
        required=True,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'placeholder': 'Brief clinical reason...'
        }),
        label="Clinical Indication"
    )
    
    priority = forms.ChoiceField(
        required=True,
        choices=[('routine', 'Routine'), ('urgent', 'Urgent')],
        initial='routine',
        widget=forms.RadioSelect,
        label="Priority"
    )
    
    def __init__(self, *args, vendor=None, **kwargs):
        super().__init__(*args, **kwargs)
        
        if vendor:
            self.fields['tests'].queryset = VendorTest.objects.filter(
                vendor=vendor,
                enabled=True
            ).order_by('name')

