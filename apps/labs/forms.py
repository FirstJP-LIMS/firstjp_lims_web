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
            'result_type', 'general_comment_template'
        ]
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., HGB'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Hemoglobin'}),
            'price': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'turnaround_override': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., 2:00:00 (HH:MM:SS)'}),
            'specimen_type': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Whole Blood'}),
            'default_units': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., g/dL'}),
            'default_reference_text': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., 12.0 - 16.0'}),
            'general_comment_template': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, vendor=None, **kwargs):
        super().__init__(*args, **kwargs)
        # CRITICAL: Filter Department choices based on the current Vendor
        if vendor:
            self.fields['assigned_department'].queryset = Department.objects.filter(vendor=vendor)
        
        self.fields['assigned_department'].widget.attrs.update({'class': 'form-select'})


# class VendorTestForm(forms.ModelForm):
#     class Meta:
#         model = VendorTest
#         exclude = ['vendor', 'slug']
#         widgets = {
#             'description': forms.Textarea(attrs={'rows': 3}),
#             'special_instructions': forms.Textarea(attrs={'rows': 2}),
#         }

#     def __init__(self, *args, **kwargs):
#         vendor = kwargs.pop('vendor', None)
#         super().__init__(*args, **kwargs)

#         self.fields['test'].queryset = GlobalTest.objects.all().order_by('name')
#         self.fields['assigned_department'].queryset = Department.objects.all().order_by('name')
        
#         # Crispy forms configuration
#         self.helper = FormHelper()
#         self.helper.form_method = 'post'
#         self.helper.form_class = 'needs-validation'
#         self.helper.form_id = 'vendor-test-form'
        
#         self.helper.layout = Layout(
#             HTML("""
#                 {% if form.non_field_errors %}
#                 <div class="alert alert-danger border-0 rounded-3 mb-4">
#                     <div class="d-flex align-items-center">
#                         <i class="bi bi-exclamation-triangle-fill me-2"></i>
#                         <div>
#                             <strong>Please correct the errors below:</strong>
#                             <ul class="mb-0 mt-1">
#                                 {% for error in form.non_field_errors %}
#                                 <li>{{ error }}</li>
#                                 {% endfor %}
#                             </ul>
#                         </div>
#                     </div>
#                 </div>
#                 {% endif %}
#             """),
            
#             Row(
#                 Column(
#                     Field('test', css_class='form-select'),
#                     css_class='col-md-6'
#                 ),
#                 Column(
#                     Field('assigned_department', css_class='form-select'),
#                     css_class='col-md-6'
#                 ),
#                 css_class='mb-3'
#             ),
            
#             Row(
#                 Column(
#                     AppendedText('price', '$', css_class='form-control'),
#                     css_class='col-md-4'
#                 ),
#                 Column(
#                     AppendedText('turnaround_time', 'hours', css_class='form-control'),
#                     css_class='col-md-4'
#                 ),
#                 Column(
#                     AppendedText('discount_percentage', '%', css_class='form-control'),
#                     css_class='col-md-4'
#                 ),
#                 css_class='mb-3'
#             ),
            
#             Row(
#                 Column(
#                     Field('is_active', css_class='form-check-input', template='forms/switch_field.html'),
#                     css_class='col-md-6'
#                 ),
#                 Column(
#                     Field('requires_special_handling', css_class='form-check-input', template='forms/switch_field.html'),
#                     css_class='col-md-6'
#                 ),
#                 css_class='mb-3'
#             ),
            
#             Field('description', rows=3, css_class='form-control', placeholder='Enter test description...'),
            
#             Field('special_instructions', rows=2, css_class='form-control', placeholder='Any special instructions...'),
            
#             HTML("""
#                 <div class="row mt-4 pt-3 border-top">
#                     <div class="col-12">
#                         <div class="d-flex gap-2 justify-content-end">
#                             <a href="{% url 'vendor_tests_list' %}" class="btn btn-outline-secondary px-4">
#                                 <i class="bi bi-x-circle me-2"></i>Cancel
#                             </a>
#                             <button type="submit" class="btn btn-wine px-4">
#                                 <i class="bi bi-check-circle me-2"></i>
#                                 {% if form.instance.pk %}Update Test{% else %}Create Test{% endif %}
#                             </button>
#                         </div>
#                     </div>
#                 </div>
#             """)
#         )


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

# class PatientForm(forms.ModelForm):
#     class Meta:
#         model = Patient
#         exclude = ['vendor', 'patient_id']
#         widgets = {
#             'date_of_birth': forms.DateInput(attrs={'type': 'date'}),
#         }


# class TestRequestForm(forms.ModelForm):
#     tests_to_order = forms.ModelMultipleChoiceField(
#         queryset=VendorTest.objects.none(),
#         widget=forms.CheckboxSelectMultiple,
#         required=True,
#         label="Select Tests"
#     )

#     class Meta:
#         model = TestRequest
#         fields = ['patient', 'clinical_history', 'priority']
#         widgets = {
#             'patient': forms.Select(attrs={'class': 'form-select'}),
#             'clinical_history': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
#             'priority': forms.Select(attrs={'class': 'form-select'}),
#         }

#     def __init__(self, *args, **kwargs):
#         vendor = kwargs.pop('vendor', None)
#         super().__init__(*args, **kwargs)

#         if vendor:
#             self.fields['patient'].queryset = Patient.objects.filter(vendor=vendor)
#             self.fields['tests_to_order'].queryset = VendorTest.objects.filter(
#                 vendor=vendor, enabled=True
#             ).select_related('vendor_test')

#         # ✅ Move crispy helper setup here
#         self.helper = FormHelper()
#         self.helper.form_method = 'post'
#         self.helper.form_class = 'needs-validation'
        
#         self.helper.layout = Layout(
#             Row(
#                 Column('patient', css_class='col-md-6 mb-3'),
#                 Column('priority', css_class='col-md-6 mb-3'),
#             ),
#             'clinical_history',
#             HTML("""
#                 <div class="mb-3">
#                     <label class="form-label fw-semibold">Select Tests</label>
#                     <div class="border rounded p-3 bg-light">
#             """),
#             Field('tests_to_order', template='forms/checkbox_select.html'),
#             HTML("""
#                     </div>
#                 </div>
#             """),
#             Submit('submit', 'Create Test Request', css_class='btn-wine w-100 py-2')
#         )

#     def save(self, commit=True):
#         instance = super().save(commit=False)
#         if commit:
#             instance.save()
#             self.save_m2m()
#             instance.requested_tests.set(self.cleaned_data['tests_to_order'])
#         return instance


class TestRequestForm(forms.ModelForm):
    tests_to_order = forms.ModelMultipleChoiceField(
        queryset=VendorTest.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        required=True,
        label="Select Tests"
    )

    class Meta:
        model = TestRequest
        fields = ['patient', 'clinical_history', 'priority']
        widgets = {
            'patient': forms.Select(attrs={'class': 'form-select'}),
            'clinical_history': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'priority': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        vendor = kwargs.pop('vendor', None)
        super().__init__(*args, **kwargs)

        if vendor:
            self.fields['patient'].queryset = Patient.objects.filter(vendor=vendor)
            # FIX: Changed 'vendor_test' to 'test'
            self.fields['tests_to_order'].queryset = VendorTest.objects.filter(
                vendor=vendor, enabled=True
            ).select_related('test')  # ✅ CORRECT FIELD NAME

        # Crispy forms setup
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.form_class = 'needs-validation'
        
        self.helper.layout = Layout(
            Row(
                Column('patient', css_class='col-md-6 mb-3'),
                Column('priority', css_class='col-md-6 mb-3'),
            ),
            'clinical_history',
            HTML("""
                <div class="mb-3">
                    <label class="form-label fw-semibold text-wine">
                        <i class="bi bi-clipboard2-check me-2"></i>
                        Select Tests
                    </label>
                    <div class="border rounded p-3 bg-light">
            """),
            Field('tests_to_order', template='forms/checkbox_select.html'),
            HTML("""
                    </div>
                    <div class="form-text">Choose the tests to include in this request</div>
                </div>
            """),
            Submit('submit', 'Create Test Request', css_class='btn-wine w-100 py-2')
        )

    def save(self, commit=True):
        instance = super().save(commit=False)
        if commit:
            instance.save()
            self.save_m2m()
            instance.requested_tests.set(self.cleaned_data['tests_to_order'])
        return instance

# class TestRequestForm(forms.ModelForm):
#     tests_to_order = forms.ModelMultipleChoiceField(
#         queryset=VendorTest.objects.none(),
#         widget=forms.CheckboxSelectMultiple,
#         required=True,
#         label="Select Tests"
#     )

#     class Meta:
#         model = TestRequest
#         fields = ['patient', 'clinical_history', 'priority']

#     def __init__(self, *args, **kwargs):
#         vendor = kwargs.pop('vendor', None)
#         super().__init__(*args, **kwargs)

#         if vendor:
#             self.fields['patient'].queryset = Patient.objects.filter(vendor=vendor)
#             self.fields['tests_to_order'].queryset = VendorTest.objects.filter(
#                 vendor=vendor, enabled=True
#             ).select_related('test')

#     def save(self, commit=True):
#         instance = super().save(commit=False)
#         if commit:
#             instance.save()
#             self.save_m2m()
#             instance.requested_tests.set(self.cleaned_data['tests_to_order'])
#         return instance

