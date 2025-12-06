from django.test import TestCase

# Create your tests here.
# tests/test_authentication.py
from django.test import TestCase, RequestFactory
from apps.accounts.models import User
from apps.tenants.models import Vendor
from apps.accounts.backends import VendorEmailBackend

class TenantAuthenticationTest(TestCase):
    def setUp(self):
        # Create two vendors
        self.vendor1 = Vendor.objects.create(name="PathCare", subdomain="pathcare")
        self.vendor2 = Vendor.objects.create(name="MedLab", subdomain="medlab")
        
        # Create same email for both vendors
        self.user1 = User.objects.create_user(
            email='patient@email.com',
            password='password1',
            vendor=self.vendor1,
            role='patient'
        )
        self.user2 = User.objects.create_user(
            email='patient@email.com',  # Same email!
            password='password2',  # Different password!
            vendor=self.vendor2,
            role='patient'
        )
        
        # Create platform admin
        self.admin = User.objects.create_superuser(
            email='admin@platform.com',
            password='adminpass',
        )
        
        self.backend = VendorEmailBackend()
        self.factory = RequestFactory()

    def test_authenticate_vendor1_user(self):
        """Test user can login to their own vendor"""
        request = self.factory.post('/login/')
        request.tenant = self.vendor1
        
        user = self.backend.authenticate(
            request=request,
            username='patient@email.com',
            password='password1'
        )
        
        self.assertIsNotNone(user)
        self.assertEqual(user.id, self.user1.id)
        self.assertEqual(user.vendor, self.vendor1)

    def test_authenticate_vendor2_user(self):
        """Test same email at different vendor works"""
        request = self.factory.post('/login/')
        request.tenant = self.vendor2
        
        user = self.backend.authenticate(
            request=request,
            username='patient@email.com',
            password='password2'  # Different password!
        )
        
        self.assertIsNotNone(user)
        self.assertEqual(user.id, self.user2.id)
        self.assertEqual(user.vendor, self.vendor2)

    def test_wrong_vendor_fails(self):
        """Test user cannot login to wrong vendor"""
        request = self.factory.post('/login/')
        request.tenant = self.vendor2  # Wrong tenant!
        
        user = self.backend.authenticate(
            request=request,
            username='patient@email.com',
            password='password1'  # Vendor1's password
        )
        
        self.assertIsNone(user)  # Should fail

    def test_platform_admin_login(self):
        """Test platform admin can login without tenant"""
        request = self.factory.post('/login/')
        request.tenant = None  # No tenant (main domain)
        
        user = self.backend.authenticate(
            request=request,
            username='admin@platform.com',
            password='adminpass'
        )
        
        self.assertIsNotNone(user)
        self.assertTrue(user.is_superuser)
        self.assertIsNone(user.vendor)