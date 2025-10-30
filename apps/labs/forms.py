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

