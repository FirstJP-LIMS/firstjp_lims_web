from django import forms
from django.db import transaction
from django.core.exceptions import ValidationError
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Row, Column, Field, HTML, Div, Submit
from crispy_forms.bootstrap import PrependedText, AppendedText
from .models import VendorTest, Department, Patient, TestRequest, Sample, PRIORITY_STATUS
from ..clinician.models import ClinicianPatientRelationship


class DepartmentForm(forms.ModelForm):
    """Form for creating and updating Vendor-scoped lab departments."""
    class Meta:
        model = Department
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Hematology'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class VendorLabTestForm(forms.ModelForm):
    """Form for defining a Lab Test within a specific Vendor's catalog."""
    
    class Meta:
        model = VendorTest
        fields = [
            # Basic Info
            'code', 'name', 'assigned_department',
            
            # Pricing & Availability
            'price', 'enabled',
            'available_for_online_booking',
            'requires_physician_approval',
            
            # Technical Details
            'specimen_type', 'method', 'platform',
            'default_units', 'result_type',
            'turnaround_override',
            
            # Patient Information
            'preparation_required',
            'preparation_instructions',
            'collection_instructions',
            'patient_friendly_description',
            'typical_reasons',
            
            # Reference Ranges
            'min_reference_value', 'max_reference_value',
            'amr_low', 'amr_high',
            'reportable_low', 'reportable_high',
            'panic_low_value', 'panic_high_value',
            
            # Advanced
            'general_comment_template',
            'enabled_for_autoverify',
        ]
        
        widgets = {
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., HGB',
                'maxlength': '64'
            }),
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Hemoglobin'
            }),
            'price': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'step': '0.01'
            }),
            
            'specimen_type': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Whole Blood, Serum'
            }),
            'method': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Spectrophotometry'
            }),
            'platform': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Cobas 6000'
            }),
            'default_units': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., g/dL'
            }),
            
            'turnaround_override': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'HH:MM:SS (e.g., 02:00:00 for 2 hours)'
            }),
            
            # Patient Information
            'preparation_instructions': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'e.g., Fast for 8-12 hours before test'
            }),
            'collection_instructions': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'e.g., First morning urine sample preferred'
            }),
            'patient_friendly_description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Explain what this test measures in simple terms'
            }),
            'typical_reasons': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'e.g., Monitoring diabetes, assessing anemia'
            }),
            
            # Numeric ranges
            'min_reference_value': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.000001'
            }),
            'max_reference_value': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.000001'
            }),
            'amr_low': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.000001'
            }),
            'amr_high': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.000001'
            }),
            'reportable_low': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.000001'
            }),
            'reportable_high': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.000001'
            }),
            'panic_low_value': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.000001'
            }),
            'panic_high_value': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.000001'
            }),
            
            'general_comment_template': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2
            }),
        }

    def __init__(self, *args, vendor=None, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Store vendor for validation
        self.vendor = vendor
        
        # Filter departments by vendor
        if vendor:
            self.fields['assigned_department'].queryset = Department.objects.filter(vendor=vendor)
        
        # Update widget classes
        self.fields['assigned_department'].widget.attrs.update({'class': 'form-select'})
        self.fields['result_type'].widget.attrs.update({'class': 'form-select'})
        
        # Add help text
        self.fields['code'].help_text = "Unique test code for this vendor (e.g., HGB, CBC, FBS)"
        self.fields['available_for_online_booking'].help_text = "Allow patients to request this test online"
        self.fields['requires_physician_approval'].help_text = "Patient orders require physician review"
        
        # Make code field case-insensitive by converting to uppercase
        self.fields['code'].widget.attrs.update({
            'style': 'text-transform: uppercase;',
            'data-validation': 'unique-code'
        })

    def clean_code(self):
        """Validate that the test code is unique for this vendor."""
        code = self.cleaned_data.get('code', '').strip().upper()
        
        if not code:
            raise ValidationError("Test code is required.")
        
        # Check for duplicate code (only for new instances or if code changed)
        if self.instance.pk:
            # Editing existing test - check if code changed
            if self.instance.code != code:
                if VendorTest.objects.filter(vendor=self.vendor, code=code).exists():
                    raise ValidationError(
                        f"A test with code '{code}' already exists for this vendor. "
                        f"Please use a different code."
                    )
        else:
            # Creating new test
            if self.vendor and VendorTest.objects.filter(vendor=self.vendor, code=code).exists():
                existing_test = VendorTest.objects.get(vendor=self.vendor, code=code)
                raise ValidationError(
                    f"Test code '{code}' is already used by '{existing_test.name}'. "
                    f"Please choose a different code."
                )
        
        return code

    def clean(self):
        """Additional validation for related fields."""
        cleaned_data = super().clean()
        
        # Validate reference ranges
        min_ref = cleaned_data.get('min_reference_value')
        max_ref = cleaned_data.get('max_reference_value')
        
        if min_ref is not None and max_ref is not None:
            if min_ref >= max_ref:
                raise ValidationError({
                    'max_reference_value': 'Maximum reference value must be greater than minimum.'
                })
        
        # Validate panic values
        panic_low = cleaned_data.get('panic_low_value')
        panic_high = cleaned_data.get('panic_high_value')
        
        if panic_low is not None and panic_high is not None:
            if panic_low >= panic_high:
                raise ValidationError({
                    'panic_high_value': 'High panic value must be greater than low panic value.'
                })
        
        # Validate AMR ranges
        amr_low = cleaned_data.get('amr_low')
        amr_high = cleaned_data.get('amr_high')
        
        if amr_low is not None and amr_high is not None:
            if amr_low >= amr_high:
                raise ValidationError({
                    'amr_high': 'AMR high value must be greater than AMR low value.'
                })
        
        # If preparation required, instructions should be provided
        if cleaned_data.get('preparation_required') and not cleaned_data.get('preparation_instructions'):
            raise ValidationError({
                'preparation_instructions': 'Please provide preparation instructions when preparation is required.'
            })
        
        return cleaned_data


# class VendorLabTestForm(forms.ModelForm):
#     """Form for defining a Lab Test within a specific Vendor's catalog."""
    
#     class Meta:
#         model = VendorTest
#         fields = [
#             # Basic Info
#             'code', 'name', 'assigned_department',
            
#             # Pricing & Availability
#             'price', 'enabled',
#             'available_for_online_booking',
#             'requires_physician_approval',
            
#             # Technical Details
#             'specimen_type', 'method', 'platform',
#             'default_units', 'result_type',
#             'turnaround_override',
            
#             # Patient Information
#             'preparation_required',
#             'preparation_instructions',
#             'collection_instructions',
#             'patient_friendly_description',
#             'typical_reasons',
            
#             # Reference Ranges
#             'min_reference_value', 'max_reference_value',
#             'amr_low', 'amr_high',
#             'reportable_low', 'reportable_high',
#             'panic_low_value', 'panic_high_value',
            
#             # Advanced
#             'general_comment_template',
#             'enabled_for_autoverify',
#         ]
        
#         widgets = {
#             'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., HGB'}),
#             'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Hemoglobin'}),
#             'price': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'step': '0.01'}),
            
#             'specimen_type': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Whole Blood, Serum'}),
#             'method': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Spectrophotometry'}),
#             'platform': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Cobas 6000'}),
#             'default_units': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., g/dL'}),
            
#             'turnaround_override': forms.TextInput(attrs={
#                 'class': 'form-control',
#                 'placeholder': 'HH:MM:SS (e.g., 02:00:00 for 2 hours)'
#             }),
            
#             # Patient Information
#             'preparation_instructions': forms.Textarea(attrs={
#                 'class': 'form-control',
#                 'rows': 3,
#                 'placeholder': 'e.g., Fast for 8-12 hours before test'
#             }),
#             'collection_instructions': forms.Textarea(attrs={
#                 'class': 'form-control',
#                 'rows': 2,
#                 'placeholder': 'e.g., First morning urine sample preferred'
#             }),
#             'patient_friendly_description': forms.Textarea(attrs={
#                 'class': 'form-control',
#                 'rows': 3,
#                 'placeholder': 'Explain what this test measures in simple terms'
#             }),
#             'typical_reasons': forms.Textarea(attrs={
#                 'class': 'form-control',
#                 'rows': 2,
#                 'placeholder': 'e.g., Monitoring diabetes, assessing anemia'
#             }),
            
#             # Numeric ranges
#             'min_reference_value': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.000001'}),
#             'max_reference_value': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.000001'}),
#             'amr_low': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.000001'}),
#             'amr_high': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.000001'}),
#             'reportable_low': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.000001'}),
#             'reportable_high': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.000001'}),
#             'panic_low_value': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.000001'}),
#             'panic_high_value': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.000001'}),
            
#             'general_comment_template': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
#         }

#     def __init__(self, *args, vendor=None, **kwargs):
#         super().__init__(*args, **kwargs)
        
#         # Filter departments by vendor
#         if vendor:
#             self.fields['assigned_department'].queryset = Department.objects.filter(vendor=vendor)
        
#         # Update widget classes
#         self.fields['assigned_department'].widget.attrs.update({'class': 'form-select'})
#         self.fields['result_type'].widget.attrs.update({'class': 'form-select'})
        
#         # Add help text
#         self.fields['available_for_online_booking'].help_text = "Allow patients to request this test online"
#         self.fields['requires_physician_approval'].help_text = "Patient orders require physician review"




class PatientForm(forms.ModelForm):
    class Meta:
        model = Patient
        exclude = ['vendor', 'patient_id']
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'gender': forms.Select(attrs={'class': 'form-select'}),
            'contact_email': forms.EmailInput(attrs={'class': 'form-control'}),
            'contact_number': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.form_class = 'needs-validation'
        
        self.helper.layout = Layout(
            Row(
                Column('first_name', css_class='col-md-6 mb-3'),
                Column('last_name', css_class='col-md-6 mb-3'),
            ),
            Row(
                Column('date_of_birth', css_class='col-md-6 mb-3'),
                Column('gender', css_class='col-md-6 mb-3'),
            ),
            Row(
                Column('contact_email', css_class='col-md-6 mb-3'),
                Column('contact_number', css_class='col-md-6 mb-3'),
            ),
            Submit('submit', 'Register Patient', css_class='btn-wine w-100 py-2')
        )
        

# class TestRequestForm(forms.ModelForm):
#     """
#     A flexible form for creating Test Requests.
#     Handles both new and existing patients.
#     Update to take patients and Clinicians 
#     """

#     # # Patient selection (for clinicians only)
#     # patient_id = forms.CharField(
#     #     required=False,
#     #     max_length=20,
#     #     widget=forms.TextInput(attrs={
#     #         'class': 'form-control',
#     #         'placeholder': 'Enter Patient ID'
#     #     }),
#     #     label="Patient ID"
#     # )
#     # ... (Existing Patient Section Fields) ...
#     existing_patient = forms.ModelChoiceField(queryset=Patient.objects.none(), required=False, label="Select Existing Patient", help_text="Choose an existing patient or enter new patient details below.")

#     first_name = forms.CharField(required=False, max_length=100, label="First Name")
#     last_name = forms.CharField(required=False, max_length=100, label="Last Name")
#     date_of_birth = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}), label="Date of Birth",
#     input_formats=['%Y-%m-%d'],  # optional
#     )


#     gender = forms.ChoiceField(
#         required=False,
#         choices=Patient.GENDER_CHOICE,
#         label="Gender"
#     )
#     contact_email = forms.EmailField(required=False, label="Contact Email")
#     contact_phone = forms.CharField(required=False, max_length=15, label="Contact Phone")

#     # --- Test Section ---
#     tests_to_order = forms.ModelMultipleChoiceField(
#         queryset=VendorTest.objects.none(),
#         widget=forms.CheckboxSelectMultiple,
#         label="Select Tests"
#     )
#     priority = forms.ChoiceField(
#         choices=PRIORITY_STATUS,
#         label="Priority",
#         initial="routine",
#     )

#     class Meta:
#         model = TestRequest
#         fields = ["existing_patient", "first_name", "last_name", "date_of_birth", "gender", "contact_email", "contact_phone", "tests_to_order",
#                   "clinical_history", "priority", "has_informed_consent", "external_referral"]
                  
#     def __init__(self, *args, **kwargs):
#         vendor = kwargs.pop('vendor', None)
#         super().__init__(*args, **kwargs)

#         if vendor:
#             self.fields["existing_patient"].queryset = Patient.objects.filter(vendor=vendor).order_by('first_name')
#             self.fields["tests_to_order"].queryset = VendorTest.objects.filter(vendor=vendor).order_by('name')

#         # Make date_of_birth field accept empty values properly
#         self.fields['date_of_birth'].empty_value = None

#     def clean_date_of_birth(self):
#         """Handle empty date values properly."""
#         dob = self.cleaned_data.get('date_of_birth')
#         if not dob:
#             return None
#         return dob

#     def clean(self):
#         cleaned_data = super().clean()
#         existing_patient = cleaned_data.get("existing_patient")
#         first_name = cleaned_data.get("first_name")
#         last_name = cleaned_data.get("last_name")
#         date_of_birth = cleaned_data.get("date_of_birth")  

#         # Require at least one patient option
#         if not existing_patient and not (first_name and last_name):
#             raise forms.ValidationError(
#                 "Please select an existing patient or provide new patient details."
#             )

#         # Require at least one test
#         tests_to_order = cleaned_data.get("tests_to_order")
#         if not tests_to_order or tests_to_order.count() == 0:
#             raise forms.ValidationError("Please select at least one test to order.")

#         return cleaned_data
    
#     @property
#     def total_order_price(self):
#         """Calculates the total price of the currently selected tests."""
#         tests = self.cleaned_data.get('tests_to_order', [])
#         total = sum(test.price for test in tests)
#         return total

#     @property
#     def patient(self):
#         existing_patient = self.cleaned_data.get("existing_patient")
#         if existing_patient:
#             return existing_patient
#         return {
#             "first_name": self.cleaned_data.get("first_name"),
#             "last_name": self.cleaned_data.get("last_name"),
#             "date_of_birth": self.cleaned_data.get("date_of_birth"),
#             "gender": self.cleaned_data.get("gender"),
#             "contact_email": self.cleaned_data.get("contact_email"),
#             "contact_phone": self.cleaned_data.get("contact_phone"),
#         }



class TestRequestForm(forms.ModelForm):
    """
    Flexible form for creating Test Requests.
    Used by:
    - Lab Staff: Can create patients on-the-fly, full catalog access
    - Clinicians: Patient selection, clinical context required
    """

    # Patient Selection Options
    existing_patient = forms.ModelChoiceField(queryset=Patient.objects.none(), required=False, label="Select Existing Patient", help_text="Choose an existing patient or enter new patient details below.", widget=forms.Select(attrs={'class': 'form-select'}))

    # New Patient Fields
    first_name = forms.CharField(required=False, max_length=100, label="First Name", widget=forms.TextInput(attrs={'class': 'form-control'}))
    
    last_name = forms.CharField(required=False, max_length=100, label="Last Name", widget=forms.TextInput(attrs={'class': 'form-control'}))
    
    date_of_birth = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        label="Date of Birth",
        input_formats=['%Y-%m-%d'],
    )

    gender = forms.ChoiceField(
        required=False,
        choices=Patient.GENDER_CHOICE,
        label="Gender",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    contact_email = forms.EmailField(
        required=False,
        label="Contact Email",
        widget=forms.EmailInput(attrs={'class': 'form-control'})
    )
    
    contact_phone = forms.CharField(
        required=False,
        max_length=15,
        label="Contact Phone",
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )

    # Test Selection
    tests_to_order = forms.ModelMultipleChoiceField(
        queryset=VendorTest.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        label="Select Tests"
    )
    
    # Clinical Context (more important for clinicians)
    clinical_indication = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Clinical reason for ordering (diagnosis, symptoms, ICD codes)...'
        }),
        label="Clinical Indication",
        help_text="Why are these tests being ordered?"
    )
    
    priority = forms.ChoiceField(
        choices=PRIORITY_STATUS,
        label="Priority",
        initial="routine",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    urgency_reason = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'placeholder': 'Required for urgent/STAT orders'
        }),
        label="Urgency Justification"
    )

    class Meta:
        model = TestRequest
        fields = [
            "existing_patient", "first_name", "last_name", "date_of_birth",
            "gender", "contact_email", "contact_phone",
            "tests_to_order", "clinical_indication", "clinical_history",
            "priority", "urgency_reason", "has_informed_consent", "external_referral"
        ]
        
        widgets = {
            'clinical_history': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Medical history, current medications, allergies...'
            }),
            'external_referral': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Referring physician/institution'
            }),
            'has_informed_consent': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
                  
    def __init__(self, *args, user=None, vendor=None, patient=None, **kwargs):
        """
        Initialize form with context.
        
        Args:
            user: Current user (lab_staff or clinician)
            vendor: Current vendor
            patient: Pre-selected patient (optional)
        """
        super().__init__(*args, **kwargs)
        
        self.user = user
        self.vendor = vendor
        self.patient = patient
        self.is_clinician = user and user.role == 'clinician'
        self.is_lab_staff = user and user.role in ['lab_staff', 'vendor_admin']

        if vendor:
            # Filter querysets by vendor
            self.fields["existing_patient"].queryset = Patient.objects.filter(
                vendor=vendor
            ).order_by('first_name', 'last_name')
            
            # Test catalog based on user role
            if self.is_clinician:
                # Clinicians see all enabled tests
                self.fields["tests_to_order"].queryset = VendorTest.objects.filter(
                    vendor=vendor,
                    enabled=True
                ).select_related('assigned_department').order_by('name')
            else:
                # Lab staff see all tests (including disabled for special cases)
                self.fields["tests_to_order"].queryset = VendorTest.objects.filter(
                    vendor=vendor
                ).select_related('assigned_department').order_by('name')
        
        # If patient pre-selected, hide patient creation fields
        if patient:
            self.fields['existing_patient'].initial = patient
            self.fields['existing_patient'].widget = forms.HiddenInput()
            # Hide new patient fields
            for field in ['first_name', 'last_name', 'date_of_birth', 'gender', 'contact_email', 'contact_phone']:
                self.fields[field].widget = forms.HiddenInput()
        
        # Clinician-specific requirements
        if self.is_clinician:
            self.fields['clinical_indication'].required = True
            self.fields['clinical_indication'].help_text = "Required for clinician orders"
        
        # Make date_of_birth accept empty values
        self.fields['date_of_birth'].empty_value = None

    def clean_date_of_birth(self):
        """Handle empty date values properly."""
        dob = self.cleaned_data.get('date_of_birth')
        if not dob:
            return None
        return dob

    def clean(self):
        cleaned_data = super().clean()
        existing_patient = cleaned_data.get("existing_patient")
        first_name = cleaned_data.get("first_name")
        last_name = cleaned_data.get("last_name")

        # Require at least one patient option
        if not existing_patient and not (first_name and last_name):
            raise forms.ValidationError(
                "Please select an existing patient or provide new patient details."
            )

        # Require at least one test
        tests_to_order = cleaned_data.get("tests_to_order")
        if not tests_to_order or tests_to_order.count() == 0:
            raise forms.ValidationError("Please select at least one test to order.")
        
        # Clinician-specific validations
        if self.is_clinician:
            # Verify clinician can order for this patient
            if existing_patient:
                try:
                    relationship = ClinicianPatientRelationship.objects.get(
                        clinician=self.user,
                        patient=existing_patient,
                        is_active=True
                    )
                    if not relationship.can_order_tests:
                        raise forms.ValidationError(
                            "You don't have permission to order tests for this patient."
                        )
                except ClinicianPatientRelationship.DoesNotExist:
                    # Auto-create relationship for clinicians
                    ClinicianPatientRelationship.objects.create(
                        clinician=self.user,
                        patient=existing_patient,
                        relationship_type='consulting',
                        established_via='Test order',
                        is_active=True,
                    )
            
            # Validate urgency reason for urgent orders
            priority = cleaned_data.get('priority')
            urgency_reason = cleaned_data.get('urgency_reason')
            
            if priority == 'urgent' and not urgency_reason:
                raise forms.ValidationError({
                    'urgency_reason': 'Justification required for urgent/STAT orders.'
                })
            
            # Clinical indication required
            if not cleaned_data.get('clinical_indication'):
                raise forms.ValidationError({
                    'clinical_indication': 'Clinical indication is required for clinician orders.'
                })

        return cleaned_data
    
    @property
    def total_order_price(self):
        """Calculate total price of selected tests."""
        if hasattr(self, 'cleaned_data'):
            tests = self.cleaned_data.get('tests_to_order', [])
            total = sum(test.price for test in tests)
            return total
        return 0

    def get_or_create_patient(self):
        """
        Get existing patient or create new one.
        Returns: Patient instance
        """
        existing_patient = self.cleaned_data.get("existing_patient")
        
        if existing_patient:
            return existing_patient
        
        # Create new patient
        patient = Patient.objects.create(
            vendor=self.vendor,
            first_name=self.cleaned_data.get("first_name"),
            last_name=self.cleaned_data.get("last_name"),
            date_of_birth=self.cleaned_data.get("date_of_birth"),
            gender=self.cleaned_data.get("gender"),
            contact_email=self.cleaned_data.get("contact_email"),
            contact_phone=self.cleaned_data.get("contact_phone"),
        )
        
        return patient
    
    def save(self, commit=True):
        """
        Save test request with proper attribution.
        """
        instance = super().save(commit=False)
        
        # Set vendor
        instance.vendor = self.vendor
        
        # Get or create patient
        patient = self.get_or_create_patient()
        instance.patient = patient
        
        # Set user attribution
        instance.requested_by = self.user
        
        # Set clinician if user is clinician
        if self.is_clinician:
            instance.ordering_clinician = self.user
            # 🆕 Auto-create relationship for newly created patients
            if patient and not ClinicianPatientRelationship.objects.filter(
                clinician=self.user,
                patient=patient
            ).exists():
                ClinicianPatientRelationship.objects.create(
                    clinician=self.user,
                    patient=patient,
                    relationship_type='primary',
                    established_via='New patient registration during test order',
                    is_active=True,
                )
        else:
            instance.ordering_clinician = None
        
        if commit:
            with transaction.atomic():
                instance.save()
                
                # Add selected tests (M2M)
                instance.requested_tests.set(self.cleaned_data['tests_to_order'])
                
                # Check if approval needed (mainly for patient self-orders)
                instance.check_approval_requirement()
                
                # Update clinician statistics
                if self.is_clinician and hasattr(self.user, 'clinician_profile'):
                    self.user.clinician_profile.increment_order_count()
        
        return instance


class SampleForm(forms.ModelForm):
    """Handles specimen/phlebotomy info for a given test request."""
    class Meta:
        model = Sample
        fields = [
            'specimen_type', 'specimen_description',
            'collected_by', 'collection_method',
            'collection_site', 'container_type',
            'volume_collected_ml', 'location'
        ]
        widgets = {
            'specimen_description': forms.Textarea(attrs={'rows': 2}),
            'collection_method': forms.TextInput(attrs={'placeholder': 'e.g., Venipuncture'}),
            'collection_site': forms.TextInput(attrs={'placeholder': 'e.g., Left Arm'}),
            'container_type': forms.TextInput(attrs={'placeholder': 'e.g., EDTA Tube'}),
            'volume_collected_ml': forms.NumberInput(attrs={'min': 0, 'step': '0.1'}),
        }
        


"""
QUALITY CONTROL...
"""
from .models import QCResult, QCLot, QCAction

class QCLotForm(forms.ModelForm):
    class Meta:
        model = QCLot
        fields = [
            'test', 'lot_number', 'level', 'manufacturer',
            'target_value', 'sd', 'explicit_low', 'explicit_high', 'units',
            'received_date', 'expiry_date', 'opened_date', 'is_active'
        ]
        widgets = {
            'received_date': forms.DateInput(attrs={'type': 'date'}),
            'expiry_date': forms.DateInput(attrs={'type': 'date'}),
            'opened_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, vendor=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Limit tests to vendor's tests if vendor provided
        if vendor is not None:
            self.fields['test'].queryset = (
                self.fields['test'].queryset.filter(vendor=vendor)
            )

    def clean(self):
        cleaned = super().clean()
        target = cleaned.get('target_value')
        sd = cleaned.get('sd')
        explicit_low = cleaned.get('explicit_low')
        explicit_high = cleaned.get('explicit_high')

        # If explicit range provided, don't require SD
        if explicit_low is not None and explicit_high is not None:
            return cleaned

        # Otherwise ensure target+sd are provided together
        if (target is None) ^ (sd is None):
            raise forms.ValidationError(
                'Provide either explicit range or both target value and SD'
            )
        return cleaned

        # Auto-calculation of low/high from target ± SD
        # Validation that expiry_date > received_date
        # Prevent opened_date > expiry_date
        # Highlight invalid SD ranges
        # Pre-populate units based on test

from decimal import Decimal, InvalidOperation
class QCEntryForm(forms.ModelForm):
    class Meta:
        model = QCResult
        fields = ['qc_lot', 'result_value', 'instrument', 'comments']
        widgets = {
            'qc_lot': forms.Select(attrs={'class': 'form-select'}),
            'result_value': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.01'}),
            'instrument': forms.Select(attrs={'class': 'form-select'}),
            'comments': forms.Textarea(attrs={'rows': 3, 'class': 'form-textarea'}),
        }

    def __init__(self, vendor, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['qc_lot'].queryset = QCLot.objects.filter(vendor=vendor, is_active=True)
        self.fields['instrument'].queryset = vendor.equipment_set.all()

    # def clean_result_value(self):
    #     value = self.cleaned_data.get("result_value")
    #     if value in (None, ''):
    #         raise forms.ValidationError("Result value is required")
    #     return value

    def clean_result_value(self):
        value = self.cleaned_data.get("result_value")
        if value in (None, '',):
            raise forms.ValidationError("Result value is required")
        try:
            return Decimal(str(value))
        except InvalidOperation:
            raise forms.ValidationError("Invalid numeric value")


class QCActionForm(forms.ModelForm):
    class Meta:
        model = QCAction
        fields = [
            'action_type',
            'description',
            'resolved',
            'resolution_notes',
        ]
        widgets = {
            'action_type': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={
                'rows': 4,
                'class': 'form-textarea',
                'placeholder': 'Describe the corrective action taken in detail...'
            }),
            'resolved': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
            'resolution_notes': forms.Textarea(attrs={
                'rows': 3,
                'class': 'form-textarea',
                'placeholder': 'Outcome after taking action...'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['resolved'].initial = False
        # Make resolution_notes required if resolved is checked
        if self.data.get('resolved'):
            self.fields['resolution_notes'].required = True

