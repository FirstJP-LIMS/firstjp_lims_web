from django.test import TestCase
from django.contrib.auth import get_user_model
from .models import Sample, TestRequest, Patient
from apps.tenants.models import Vendor

# Create your tests here.

class SampleModelTest(TestCase):
    def setUp(self):
        self.vendor = Vendor.objects.create(name="Test Vendor")
        self.patient = Patient.objects.create(first_name="John", last_name="Doe", date_of_birth="1990-01-01")
        self.test_request = TestRequest.objects.create(
            vendor=self.vendor,
            patient=self.patient,
            request_id="REQ001"
        )

    def test_sample_id_is_auto_generated(self):
        sample = Sample.objects.create(
            vendor=self.vendor,
            patient=self.patient,
            test_request=self.test_request,
            specimen_type="Blood"
        )
        self.assertIsNotNone(sample.sample_id)
        self.assertNotEqual(sample.sample_id, "")
        self.assertTrue(sample.sample_id.startswith("SMP"))
        print(f"Auto-generated sample_id: {sample.sample_id}")
