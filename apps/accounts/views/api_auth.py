
# ==============================================
# FUTURE REST API ARCHITECTURE (For Reference & Planning)
# ==============================================

"""
REST API IMPLEMENTATION STRATEGY:

When you scale to a separate frontend (React/Vue/Next.js), you'll create 
REST endpoints that mirror this workflow:

1. REQUEST RESET
   POST /api/v1/auth/password-reset/
   Body: {"email": "user@example.com"}
   Response: {"status": "success", "message": "Reset email sent"}
   
   Backend:
   - Validate email belongs to current tenant (via subdomain/header)
   - Generate token & uid
   - Queue email task (Celery)
   - Return 202 Accepted immediately

2. VERIFY TOKEN
   GET /api/v1/auth/password-reset/verify/{uid}/{token}/
   Response: 
   - 200 OK if valid
   - 400 Bad Request if expired/invalid
   
   Frontend uses this to show/hide password reset form

3. CONFIRM NEW PASSWORD
   POST /api/v1/auth/password-reset/confirm/
   Body: {
       "uid": "abc123",
       "token": "xyz789",
       "new_password": "SecurePass123!",
       "confirm_password": "SecurePass123!"
   }
   Response: {"status": "success", "message": "Password reset successful"}

4. TOKEN MANAGEMENT
   - Use Django's default_token_generator (same as current)
   - Tokens expire after 24 hours (configurable)
   - One-time use only
   - Rate limiting on reset requests (prevent abuse)

MULTI-TENANCY HANDLING IN REST API:
   - Option A: Subdomain routing (tenant1.medvuno.com/api/...)
   - Option B: Tenant ID in request header (X-Tenant-ID)
   - Option C: Tenant slug in URL path (/api/v1/tenant/{slug}/auth/...)
   
   Recommended: Subdomain routing (matches your current Django setup)

AUTHENTICATION FLOW:
   - Django session auth (current) continues to work
   - REST API uses JWT tokens for stateless auth
   - Shared User model across both systems
   - DRF's TokenAuthentication or SimpleJWT for API
"""

# ======================================================
# EXAMPLE REST API VIEWS (Django REST Framework - Future Implementation)
# =======================================================

"""
# apps/accounts/api/views.py

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from .serializers import (
    PasswordResetRequestSerializer,
    PasswordResetConfirmSerializer
)


@api_view(['POST'])
@permission_classes([AllowAny])
def password_reset_request(request):
    '''
    REST endpoint for password reset request.
    
    POST /api/v1/auth/password-reset/
    Body: {"email": "user@example.com"}
    '''
    serializer = PasswordResetRequestSerializer(
        data=request.data,
        context={'request': request}
    )
    
    if serializer.is_valid():
        # Queue email task (async with Celery)
        serializer.save()
        
        return Response(
            {
                'status': 'success',
                'message': 'If an account exists with this email, a reset link will be sent.'
            },
            status=status.HTTP_202_ACCEPTED
        )
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([AllowAny])
def password_reset_verify(request, uidb64, token):
    '''
    Verify password reset token validity.
    
    GET /api/v1/auth/password-reset/verify/{uid}/{token}/
    '''
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
        
        # Validate tenant context
        tenant = getattr(request, 'tenant', None)
        if tenant and user.vendor != tenant:
            return Response(
                {'error': 'Invalid reset link'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if default_token_generator.check_token(user, token):
            return Response({
                'status': 'success',
                'message': 'Token is valid',
                'uid': uidb64,
                'email': user.email
            })
        else:
            return Response(
                {'error': 'Token has expired or is invalid'},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        return Response(
            {'error': 'Invalid reset link'},
            status=status.HTTP_400_BAD_REQUEST
        )


@api_view(['POST'])
@permission_classes([AllowAny])
def password_reset_confirm(request):
    '''
    Set new password after token verification.
    
    POST /api/v1/auth/password-reset/confirm/
    Body: {
        "uid": "abc123",
        "token": "xyz789",
        "new_password": "SecurePass123!",
        "confirm_password": "SecurePass123!"
    }
    '''
    serializer = PasswordResetConfirmSerializer(
        data=request.data,
        context={'request': request}
    )
    
    if serializer.is_valid():
        serializer.save()
        
        return Response({
            'status': 'success',
            'message': 'Password has been reset successfully'
        })
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
"""


# ============================================================================
# FUTURE REST API SERIALIZERS (For Reference)
# To be used in replacement of DJango forms
# =====================================================

"""
# apps/accounts/api/serializers.py

from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.core.mail import send_mail
from django.template.loader import render_to_string
import re

User = get_user_model()


class PasswordResetRequestSerializer(serializers.Serializer):
    '''
    Serializer for password reset request.
    
    TENANT CONTEXT:
    - Extract tenant from request (subdomain or header)
    - Only find users belonging to that tenant
    '''
    email = serializers.EmailField()
    
    def validate_email(self, value):
        '''Validate email format and normalize.'''
        return value.lower().strip()
    
    def save(self):
        '''
        Generate reset token and send email.
        
        ASYNC PROCESSING:
        - In production, this should queue a Celery task
        - Don't block API response waiting for email delivery
        '''
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)
        email = self.validated_data['email']
        
        # Find user (tenant-scoped)
        try:
            if tenant:
                user = User.objects.get(email=email, vendor=tenant, is_active=True)
            else:
                # Learning portal (vendor=None)
                user = User.objects.get(email=email, vendor=None, is_active=True)
            
            # Generate token
            token = default_token_generator.make_token(user)
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            
            # Build reset URL (frontend URL, not Django)
            reset_url = f"{settings.FRONTEND_URL}/reset-password/{uid}/{token}/"
            
            # Queue email task (Celery)
            from apps.accounts.tasks import send_password_reset_email
            send_password_reset_email.delay(
                user_id=user.id,
                reset_url=reset_url,
                tenant_id=tenant.id if tenant else None
            )
            
        except User.DoesNotExist:
            # Don't reveal if email exists (security)
            pass
        
        return {'status': 'sent'}


class PasswordResetConfirmSerializer(serializers.Serializer):
    '''
    Serializer for password reset confirmation.
    
    VALIDATION:
    - Check token validity
    - Enforce password strength (same rules as form)
    - Ensure passwords match
    '''
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(min_length=8, write_only=True)
    confirm_password = serializers.CharField(min_length=8, write_only=True)
    
    def validate(self, data):
        '''Validate token and passwords.'''
        # Decode uid
        try:
            uid = force_str(urlsafe_base64_decode(data['uid']))
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            raise serializers.ValidationError({'uid': 'Invalid reset link'})
        
        # Validate tenant context
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)
        
        if tenant and user.vendor != tenant:
            raise serializers.ValidationError({'uid': 'Invalid reset link'})
        
        # Check token validity
        if not default_token_generator.check_token(user, data['token']):
            raise serializers.ValidationError({'token': 'Token has expired or is invalid'})
        
        # Validate passwords match
        if data['new_password'] != data['confirm_password']:
            raise serializers.ValidationError({'confirm_password': 'Passwords do not match'})
        
        # Store user for save method
        self.user = user
        
        return data
    
    def validate_new_password(self, value):
        '''
        Enforce password strength requirements.
        
        IDENTICAL TO DJANGO FORM:
        - Same validation rules apply
        - Centralized password policy
        '''
        if len(value) < 8:
            raise serializers.ValidationError("Password must be at least 8 characters long.")
        
        if not re.search(r'[A-Z]', value):
            raise serializers.ValidationError("Password must contain at least one uppercase letter.")
        
        if not re.search(r'[a-z]', value):
            raise serializers.ValidationError("Password must contain at least one lowercase letter.")
        
        if not re.search(r'\d', value):
            raise serializers.ValidationError("Password must contain at least one number.")
        
        if not re.search(r'[!@#$%^&*(),.?\":{}|<>]', value):
            raise serializers.ValidationError("Password must contain at least one special character.")
        
        weak_patterns = ['password', '12345678', 'qwerty', 'abc123', 'letmein', 'welcome', 'admin']
        for pattern in weak_patterns:
            if pattern in value.lower():
                raise serializers.ValidationError(f"Password cannot contain common patterns like '{pattern}'.")
        
        return value
    
    def save(self):
        '''Set new password and log the change.'''
        user = self.user
        user.set_password(self.validated_data['new_password'])
        user.save()
        
        # Log password reset
        logger.info(f"Password reset via API for user: {user.email}")
        
        # Send confirmation email (async)
        from apps.accounts.tasks import send_password_changed_notification
        send_password_changed_notification.delay(user.id)
        
        return user
"""


# ============================================================================
# FUTURE REST API URLS (For Reference)
# ============================================================================

"""
# apps/accounts/api/urls.py

from django.urls import path
from . import views

app_name = 'account_api'

urlpatterns = [
    # ============================================================
    # AUTHENTICATION API
    # ============================================================
    # Login (JWT token generation)
    path('auth/login/', views.LoginAPIView.as_view(), name='login'),
    
    # Logout (token invalidation)
    path('auth/logout/', views.LogoutAPIView.as_view(), name='logout'),
    
    # Token refresh
    path('auth/token/refresh/', views.TokenRefreshAPIView.as_view(), name='token_refresh'),
    
    # ============================================================
    # REGISTRATION API
    # ============================================================
    # Tenant-scoped registration
    path('auth/register/<str:role_name>/', views.RegisterAPIView.as_view(), name='register'),
    
    # ============================================================
    # PASSWORD RESET API
    # ============================================================
    # Request password reset
    path(
        'auth/password-reset/',
        views.password_reset_request,
        name='password_reset_request'
    ),
    
    # Verify reset token (optional - frontend can try confirm directly)
    path(
        'auth/password-reset/verify/<str:uidb64>/<str:token>/',
        views.password_reset_verify,
        name='password_reset_verify'
    ),
    
    # Confirm new password
    path(
        'auth/password-reset/confirm/',
        views.password_reset_confirm,
        name='password_reset_confirm'
    ),
    
    # ============================================================
    # USER PROFILE API
    # ============================================================
    # Get current user
    path('users/me/', views.CurrentUserAPIView.as_view(), name='current_user'),
    
    # Update profile
    path('users/me/update/', views.UpdateProfileAPIView.as_view(), name='update_profile'),
    
    # Change password (authenticated)
    path('users/me/change-password/', views.ChangePasswordAPIView.as_view(), name='change_password'),
]


# ============================================================
# MAIN PROJECT URLs (apps/config/urls.py)
# ============================================================

from django.urls import path, include

urlpatterns = [
    # Django views (current)
    path('accounts/', include('apps.accounts.urls')),
    
    # REST API (future)
    path('api/v1/accounts/', include('apps.accounts.api.urls')),
    
    # Other apps...
]
"""
