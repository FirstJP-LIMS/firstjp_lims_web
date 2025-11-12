from django import forms
from .models import VendorTest, Department, Patient, TestRequest
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Row, Column, Submit

from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Row, Column, Field, HTML, Div
from crispy_forms.bootstrap import PrependedText, AppendedText
from .models import VendorTest
from django import forms
from .models import Department, VendorTest


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
            'code', 'name', 'assigned_department', 
            'price', 'turnaround_override', 'enabled', 
            'specimen_type', 'default_units', 'default_reference_text', 
            'result_type', 'min_reference_value', 'max_reference_value', 'general_comment_template'
        ]
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., HGB'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Hemoglobin'}),
            'price': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'turnaround_override': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., 2:00:00 (HH:MM:SS)'}),
            'specimen_type': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Whole Blood'}),
            'default_units': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., g/dL'}),
            'default_reference_text': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., 12.0 - 16.0'}),
            'min_reference_value': forms.NumberInput(attrs={'class': 'form-control','placeholder': 'e.g., 12.02'}),
            'max_reference_value': forms.NumberInput(attrs={'class': 'form-control','placeholder': 'e.g., 15.02'}),
            'general_comment_template': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, vendor=None, **kwargs):
        super().__init__(*args, **kwargs)
        # CRITICAL: Filter Department choices based on the current Vendor
        if vendor:
            self.fields['assigned_department'].queryset = Department.objects.filter(vendor=vendor)
        
        self.fields['assigned_department'].widget.attrs.update({'class': 'form-select'})


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
        

class TestRequestForm(forms.ModelForm):
    """
    A flexible form for creating Test Requests.
    Handles both new and existing patients.
    """

    # ... (Existing Patient Section Fields) ...
    existing_patient = forms.ModelChoiceField(
        queryset=Patient.objects.none(),
        required=False,
        label="Select Existing Patient",
        help_text="Choose an existing patient or enter new patient details below."
    )
    first_name = forms.CharField(required=False, max_length=100, label="First Name")
    last_name = forms.CharField(required=False, max_length=100, label="Last Name")
    date_of_birth = forms.DateField(
    required=False,
    widget=forms.DateInput(attrs={'type': 'date'}),
    label="Date of Birth",
    input_formats=['%Y-%m-%d'],  # optional
    )

    gender = forms.ChoiceField(
        required=False,
        choices=Patient.GENDER_CHOICE,
        label="Gender"
    )
    contact_email = forms.EmailField(required=False, label="Contact Email")
    contact_phone = forms.CharField(required=False, max_length=15, label="Contact Phone")

    # --- Test Section ---
    tests_to_order = forms.ModelMultipleChoiceField(
        queryset=VendorTest.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        label="Select Tests"
    )

    class Meta:
        model = TestRequest
        fields = ["existing_patient", "first_name", "last_name", "date_of_birth",
                  "gender", "contact_email", "contact_phone", "tests_to_order",
                  "clinical_history", "priority", "has_informed_consent", "external_referral"]
                  
    def __init__(self, *args, **kwargs):
        vendor = kwargs.pop('vendor', None)
        super().__init__(*args, **kwargs)

        if vendor:
            self.fields["existing_patient"].queryset = Patient.objects.filter(vendor=vendor)
            self.fields["tests_to_order"].queryset = VendorTest.objects.filter(vendor=vendor).order_by('name')

        # Make date_of_birth field accept empty values properly
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
        date_of_birth = cleaned_data.get("date_of_birth")  

        # Require at least one patient option
        if not existing_patient and not (first_name and last_name):
            raise forms.ValidationError(
                "Please select an existing patient or provide new patient details."
            )

        # Require at least one test
        tests_to_order = cleaned_data.get("tests_to_order")
        if not tests_to_order or tests_to_order.count() == 0:
            raise forms.ValidationError("Please select at least one test to order.")

        return cleaned_data
    
    @property
    def total_order_price(self):
        """Calculates the total price of the currently selected tests."""
        tests = self.cleaned_data.get('tests_to_order', [])
        total = sum(test.price for test in tests)
        return total

    @property
    def patient(self):
        existing_patient = self.cleaned_data.get("existing_patient")
        if existing_patient:
            return existing_patient
        return {
            "first_name": self.cleaned_data.get("first_name"),
            "last_name": self.cleaned_data.get("last_name"),
            "date_of_birth": self.cleaned_data.get("date_of_birth"),
            "gender": self.cleaned_data.get("gender"),
            "contact_email": self.cleaned_data.get("contact_email"),
            "contact_phone": self.cleaned_data.get("contact_phone"),
        }


from . models import Sample
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
        