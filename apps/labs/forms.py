from django import forms
from .models import VendorTest, GlobalTest, Department, Patient, TestRequest


class VendorTestForm(forms.ModelForm):
    class Meta:
        model = VendorTest
        exclude = ['vendor', 'slug']

    def __init__(self, *args, **kwargs):
        vendor = kwargs.pop('vendor', None)
        super().__init__(*args, **kwargs)

        self.fields['test'].queryset = GlobalTest.objects.all().order_by('name')
        self.fields['assigned_department'].queryset = Department.objects.all().order_by('name')



# class VendorTestForm(forms.ModelForm):
#     assigned_department = forms.ModelChoiceField(
#         queryset=Department.objects.all().order_by('name'),
#         required=True,
#         help_text="Department responsible for this test"
#     )

#     class Meta:
#         model = VendorTest
#         exclude = ['vendor', 'slug']

#     def __init__(self, *args, **kwargs):
#         self.vendor = kwargs.pop('vendor', None)
#         super().__init__(*args, **kwargs)

#         self.fields['test'].queryset = GlobalTest.objects.all().order_by('name')

#     def clean(self):
#         cleaned_data = super().clean()
#         test = cleaned_data.get('test')
#         assigned_department = cleaned_data.get('assigned_department')

#         # Validation 1: Check department match
#         if test and assigned_department and test.department != assigned_department:
#             self.add_error('assigned_department', "Selected department does not match the test's assigned department.")

#         # Validation 2: Prevent duplicate VendorTest
#         if self.vendor and test:
#             existing = VendorTest.objects.filter(vendor=self.vendor, test=test)
#             if self.instance.pk:
#                 existing = existing.exclude(pk=self.instance.pk)
#             if existing.exists():
#                 self.add_error('test', "This test is already configured for the selected vendor.")

#         return cleaned_data


class PatientForm(forms.ModelForm):
    class Meta:
        model = Patient
        exclude = ['vendor', 'patient_id']
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date'}),
        }


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

    def __init__(self, *args, **kwargs):
        vendor = kwargs.pop('vendor', None)
        super().__init__(*args, **kwargs)

        if vendor:
            self.fields['patient'].queryset = Patient.objects.filter(vendor=vendor)
            self.fields['tests_to_order'].queryset = VendorTest.objects.filter(
                vendor=vendor, enabled=True
            ).select_related('test')

    def save(self, commit=True):
        instance = super().save(commit=False)
        if commit:
            instance.save()
            self.save_m2m()
            instance.requested_tests.set(self.cleaned_data['tests_to_order'])
        return instance

