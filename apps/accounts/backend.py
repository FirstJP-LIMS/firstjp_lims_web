# apps/accounts/backends.py
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model

User = get_user_model()


# Allowed role groups
TENANT_ALLOWED = {'vendor_admin', 'lab_staff', 'clinician', 'patient'}
PLATFORM_ALLOWED = {'platform_admin'}  # platform admins only on main platform
LEARN_ALLOWED = {'learner', 'facilitator'}


class VendorEmailBackend(ModelBackend):
    """
    Authenticate using email + tenant (vendor).

    Behavior:
    - If request.is_learning_portal: authenticate only vendor=None and role in LEARN_ALLOWED
    - If tenant present: authenticate vendor-scoped users and disallow LEARN roles
    - If no tenant and not learning portal: platform-level auth (platform admins only)
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None or password is None:
            return None

        tenant = getattr(request, 'tenant', None)
        is_learning = getattr(request, 'is_learning_portal', False)

        # Normalize username for case-insensitive match
        lookup_email = username

        try:
            if is_learning:
                # Learning portal: only vendor=None and learner/facilitator roles
                user = User.objects.get(
                    email__iexact=lookup_email,
                    vendor__isnull=True,
                    role__in=LEARN_ALLOWED,
                    is_active=True
                )
            elif tenant:
                # Tenant-scoped authentication: restrict to tenant allowed roles
                user = User.objects.get(
                    email__iexact=lookup_email,
                    vendor=tenant,
                    is_active=True
                )
                # Reject learning roles inside tenant context explicitly
                if user.role not in TENANT_ALLOWED:
                    return None
            else:
                # Platform-level (main domain): only platform admins (vendor=None)
                user = User.objects.get(
                    email__iexact=lookup_email,
                    vendor__isnull=True,
                    is_active=True
                )
                if user.role not in PLATFORM_ALLOWED and not user.is_superuser:
                    return None

        except User.DoesNotExist:
            return None
        except User.MultipleObjectsReturned:
            # With unique_together (email, vendor) this should not happen; handle gracefully
            return None

        # Verify password & whether the user can authenticate
        if user.check_password(password) and self.user_can_authenticate(user):
            return user

        return None

    def get_user(self, user_id):
        try:
            user = User.objects.get(pk=user_id)
            return user if self.user_can_authenticate(user) else None
        except User.DoesNotExist:
            return None


# from django.contrib.auth.backends import ModelBackend
# from django.contrib.auth import get_user_model

# User = get_user_model()

# class VendorEmailBackend(ModelBackend):
#     """
#     Authenticate using email + tenant (vendor).
    
#     Handles two authentication scenarios:
#     1. Tenant-scoped users: Must match email AND vendor
#     2. Platform admins: email with vendor=None (global access)
#     """

#     def authenticate(self, request, username=None, password=None, **kwargs):
#         if username is None or password is None:
#             return None

#         # Get tenant from request (set by middleware)
#         tenant = getattr(request, 'tenant', None)
        
#         try:
#             if tenant:
#                 # Tenant-scoped authentication
#                 # Find user with matching email AND vendor
#                 user = User.objects.get(
#                     email__iexact=username,
#                     vendor=tenant,
#                     is_active=True  # ✅ Only active users
#                 )
#             else:
#                 # Platform-level authentication (no tenant subdomain)
#                 # Only allow platform admins (vendor=None) to login on main domain
#                 user = User.objects.get(
#                     email__iexact=username,
#                     vendor__isnull=True,
#                     is_active=True
#                 )
#         except User.DoesNotExist:
#             # User not found for this tenant/email combination
#             return None
#         except User.MultipleObjectsReturned:
#             # This should never happen with unique_together constraint
#             # But handle it gracefully just in case
#             return None

#         # Verify password
#         if user.check_password(password) and self.user_can_authenticate(user):
#             return user
        
#         return None

#     def get_user(self, user_id):
#         """
#         Retrieve user by ID (used by Django session authentication).
#         """
#         try:
#             user = User.objects.get(pk=user_id)
#             return user if self.user_can_authenticate(user) else None
#         except User.DoesNotExist:
#             return None


