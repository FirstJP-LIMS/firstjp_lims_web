# apps/accounts/backends.py
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model

User = get_user_model()

class VendorEmailBackend(ModelBackend):
    """
    Authenticate using email + tenant (vendor).
    
    Handles two authentication scenarios:
    1. Tenant-scoped users: Must match email AND vendor
    2. Platform admins: email with vendor=None (global access)
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None or password is None:
            return None

        # Get tenant from request (set by middleware)
        tenant = getattr(request, 'tenant', None)
        
        try:
            if tenant:
                # Tenant-scoped authentication
                # Find user with matching email AND vendor
                user = User.objects.get(
                    email__iexact=username,
                    vendor=tenant,
                    is_active=True  # ✅ Only active users
                )
            else:
                # Platform-level authentication (no tenant subdomain)
                # Only allow platform admins (vendor=None) to login on main domain
                user = User.objects.get(
                    email__iexact=username,
                    vendor__isnull=True,
                    is_active=True
                )
        except User.DoesNotExist:
            # User not found for this tenant/email combination
            return None
        except User.MultipleObjectsReturned:
            # This should never happen with unique_together constraint
            # But handle it gracefully just in case
            return None

        # Verify password
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        
        return None

    def get_user(self, user_id):
        """
        Retrieve user by ID (used by Django session authentication).
        """
        try:
            user = User.objects.get(pk=user_id)
            return user if self.user_can_authenticate(user) else None
        except User.DoesNotExist:
            return None




# # apps/accounts/backends.py
# from django.contrib.auth.backends import ModelBackend
# from django.db.models import Q
# from .models import User

# class VendorEmailBackend(ModelBackend):
#     """
#     Authenticate using email + tenant (vendor). If tenant isn't present, allow platform-level users (vendor is None).
#     """

#     def authenticate(self, request, username=None, password=None, **kwargs):
#         if username is None or password is None:
#             return None

#         tenant = getattr(request, 'tenant', None)
#         # tenant scoped lookup
#         try:
#             if tenant:
#                 # exact match to vendor
#                 user = User.objects.get(email__iexact=username, vendor=tenant)
#             else:
#                 # platform-level login, vendor must be null
#                 user = User.objects.get(email__iexact=username, vendor__isnull=True)
#         except User.DoesNotExist:
#             return None

#         if user.check_password(password) and self.user_can_authenticate(user):
#             return user
#         return None


# # apps/accounts/backends.py
# from django.contrib.auth.backends import ModelBackend
# from .models import User, UserTenantMembership
# from django.contrib.auth.backends import ModelBackend
# from .models import User

# class TenantBackend(ModelBackend):
#     """
#     Authenticate a user scoped to a tenant (subdomain) or globally for platform users.
#     """

#     def authenticate(self, request, username=None, password=None, **kwargs):
#         if not username:
#             return None

#         tenant = getattr(request, "tenant", None)

#         try:
#             user = User.objects.get(email__iexact=username)
#         except User.DoesNotExist:
#             return None

#         if not user.check_password(password) or not user.is_active:
#             return None

#         # -------------------------------
#         # Platform-level login
#         # -------------------------------
#         if tenant is None:
#             if user.is_platform_admin or user.role in [User.ROLE_STUDENT, User.ROLE_FACILITATOR]:
#                 return user
#             return None

#         # -------------------------------
#         # Tenant-level login
#         # -------------------------------
#         if user.memberships.filter(vendor=tenant, is_active=True).exists():
#             return user

#         # User does not belong to this tenant
#         return None

#     # Optional: enforce get_user for completeness
#     def get_user(self, user_id):
#         try:
#             return User.objects.get(pk=user_id)
#         except User.DoesNotExist:
#             return None










