# app/accounts/views.py
from django.shortcuts import render, redirect, get_object_or_404, Http404
from django.views.generic import TemplateView
from apps.tenants.models import Vendor
from ..forms import RegistrationForm, TenantAuthenticationForm, VendorProfile, VendorProfileForm, TenantPasswordResetForm
from django.urls import reverse, reverse_lazy
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import user_passes_test, login_required
from django.shortcuts import render, redirect
from django_ratelimit.decorators import ratelimit
from django.contrib.auth import get_user_model
import logging
from django.contrib.messages import get_messages

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


User = get_user_model()

# role groups
LEARN_ALLOWED = ['learner', 'facilitator']
TENANT_ALLOWED = ['vendor_admin', 'lab_staff', 'patient', 'clinician']

def tenant_register_by_role(request, role_name):
    """
        Handles registration for tenant-scoped roles (lab_staff, clinician, patient, vendor_admin), scoped to the current tenant.
    """
    tenant = getattr(request, 'tenant', None)

    if role_name not in TENANT_ALLOWED:
        raise Http404("Invalid registration path or user role.")

    if not tenant:
        messages.error(request, "Tenant could not be resolved.")
        return redirect('account:login')

    if request.method == 'POST':
        form = RegistrationForm(
            request.POST,
            vendor=tenant,
            forced_role=role_name,
            is_learning_portal=False
        )
        if form.is_valid():
            user = form.save(vendor=tenant) # save data

            # Customize success message for patients
            if role_name == 'patient':
                messages.success(
                    request,
                    f"Welcome! Your patient account has been created for {tenant.name}. "
                    f"Please check your email to verify your account."
                )
            else:
                messages.success(
                    request,
                    f"{role_name.replace('_',' ').title()} account created for {tenant.name}."
                )
            
            return redirect(reverse('account:login'))
    else:
        form = RegistrationForm(
            vendor=tenant,
            forced_role=role_name,
            is_learning_portal=False
        )

    return render(request, 'authentication/register.html', {
        'form': form,
        'tenant': tenant,
        'role_name': role_name.replace('_',' ').title(),
    })


def learn_register(request, role_name):
    """
    Registration entry-point for learn.medvuno.com; only learner/facilitator allowed.
    """

    if not getattr(request, 'is_learning_portal', False):
        raise Http404("Not found.")

    if role_name not in LEARN_ALLOWED:
        raise Http404("Invalid registration role.")

    if request.method == 'POST':
        form = RegistrationForm(
            request.POST,
            vendor=None,
            forced_role=role_name,
            is_learning_portal=True
        )
        if form.is_valid():
            form.save()
            messages.success(request, f"{role_name.title()} account created.")
            return redirect(reverse('account:login'))
    else:
        form = RegistrationForm(
            vendor=None,
            forced_role=role_name,
            is_learning_portal=True
        )

    return render(request, 'authentication/register.html', {
        'form': form,
        'role_name': role_name.title(),
    })


# @ratelimit(key='ip', rate='5/m', method='POST')
def tenant_login(request):
    storage = get_messages(request)
    for message in storage:
        pass
    
    tenant = getattr(request, 'tenant', None)
    is_learning = getattr(request, 'is_learning_portal', False)

    if request.method == 'POST':
        form = TenantAuthenticationForm(request, data=request.POST)
        try:
            if form.is_valid():
                user = form.get_user()

                # 1️⃣ Learning portal login
                if is_learning:
                    # Only learner/facilitator allowed, vendor must be None
                    if user.vendor is not None or user.role not in LEARN_ALLOWED:
                        messages.error(request, "This account cannot access the learning portal.")
                        return redirect(reverse('account:login'))

                    login(request, user)
                    messages.success(request, f"Welcome, {user.first_name or user.email}")
                    # return redirect(reverse('learn:index'))  # create a learn dashboard route
                    if user.role == "learner":
                        return redirect(reverse('learn:index'))  # create a learn dashboard route
                    elif user.role == "facilitator":
                        return redirect(reverse('learn:facilitator_dashboard'))  # create a learn dashboard route

                # 2️⃣ Platform Admin: global access
                if getattr(user, 'is_platform_admin', False):
                    login(request, user)
                    # messages.success(request, f"Welcome back, {user.first_name}")
                    return redirect(reverse('dashboard'))

                # 3️⃣ Tenant validation (vendor sites)
                if not tenant:
                    messages.error(request, "No tenant could be resolved. Access denied.")
                    return redirect(reverse('no_tenant'))

                if not user.vendor or user.vendor.internal_id != tenant.internal_id:
                    messages.error(request, "This account does not belong to this tenant.")
                    return redirect(reverse('account:login'))

                # Reject learning roles for tenant domains
                if user.role not in TENANT_ALLOWED:
                    messages.error(request, "This account role cannot access this tenant.")
                    return redirect(reverse('account:login'))

                login(request, user)
                messages.success(request, f"Welcome, {user.email}")

                # role routing
                if user.role in ['vendor_admin', 'lab_staff']:
                    print("Logged-in Successfully")
                    return redirect(reverse('labs:vendor_dashboard'))
                elif user.role == 'patient':
                    return redirect(reverse('patient:patient_dashboard'))
                elif user.role == 'clinician':
                    return redirect(reverse('clinician:clinician_dashboard'))
                else:
                    return redirect(reverse('account:login'))
        except Exception as e:
            import traceback
            print(traceback.format_exc()) # This will show the full error in your console
            messages.error(request, f"Internal Server Error: {str(e)}")
        else:
            # ADD THIS FOR DEBUGGING
            print(f"Form Errors: {form.errors.as_json()}") 
            messages.error(request, "Invalid username or password.")
    
    else:
        form = TenantAuthenticationForm(request)

    context = {
        'form': form,
        'tenant': tenant
    }
    return render(request, 'authentication/login.html', context)


def tenant_logout(request):
    logout(request)
    messages.info(request, "You have been logged out successfully.")
    return redirect(reverse_lazy('account:login'))


"""
    Tasks to complete:
    Password Resetting...
"""

# apps/accounts/views.py (Password Reset Views)
# from django.shortcuts import render, redirect
# from django.contrib.auth.views import (
#     PasswordResetView, 
#     PasswordResetDoneView,
#     PasswordResetConfirmView, 
#     PasswordResetCompleteView
# )
# from django.contrib.auth.tokens import default_token_generator
# from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
# from django.utils.encoding import force_bytes, force_str
# from django.core.mail import send_mail
# from django.template.loader import render_to_string
# from django.urls import reverse_lazy, reverse
# from django.contrib import messages
# from django.conf import settings
# from ..forms import TenantPasswordResetForm, TenantSetPasswordForm


# class TenantPasswordResetView(PasswordResetView):
#     template_name = 'authentication/password_reset/password_reset_form.html'
#     form_class = TenantPasswordResetForm
#     success_url = reverse_lazy('account:password_reset_done')
    
#     def get_form_kwargs(self):
#         kwargs = super().get_form_kwargs()
#         kwargs['tenant'] = getattr(self.request, 'tenant', None)
#         return kwargs


# class TenantPasswordResetDoneView(PasswordResetDoneView):
#     """
#     Step 2: Confirmation that reset email was sent.
    
#     ARCHITECTURE NOTES:
#     - Django: Static template with message
#     - Future REST: Not needed (API returns JSON immediately)
#     """
#     template_name = 'authentication/password_reset/password_reset_done.html'
    
#     def get_context_data(self, **kwargs):
#         context = super().get_context_data(**kwargs)
#         context['tenant'] = getattr(self.request, 'tenant', None)
#         context['is_learning_portal'] = getattr(self.request, 'is_learning_portal', False)
#         return context


# class TenantPasswordResetConfirmView(PasswordResetConfirmView):
#     """
#     Step 3: User clicks email link and sets new password.
    
#     ARCHITECTURE NOTES:
#     - Django: GET shows form, POST processes new password
#     - Future REST: 
#         - GET /api/v1/auth/password-reset/verify/{uid}/{token}/ → Validate token
#         - POST /api/v1/auth/password-reset/confirm/ → Set new password
#     """
#     template_name = 'authentication/password_reset/password_reset_confirm.html'
#     form_class = TenantSetPasswordForm
#     success_url = reverse_lazy('account:password_reset_complete')
    
#     def get_context_data(self, **kwargs):
#         context = super().get_context_data(**kwargs)
#         context['tenant'] = getattr(self.request, 'tenant', None)
#         context['is_learning_portal'] = getattr(self.request, 'is_learning_portal', False)
        
#         # Check if token is valid
#         if self.validlink:
#             context['validlink'] = True
#         else:
#             context['validlink'] = False
            
#         return context
    
#     def form_valid(self, form):
#         """Log password reset success."""
#         user = form.save()
#         logger.info(f"Password successfully reset for user: {user.email}")
#         messages.success(
#             self.request, 
#             "Your password has been reset successfully. You can now log in with your new password."
#         )
#         return super().form_valid(form)


# class TenantPasswordResetCompleteView(PasswordResetCompleteView):
#     """
#     Step 4: Success page with link to login.
    
#     ARCHITECTURE NOTES:
#     - Django: Static success template
#     - Future REST: Not needed (handled client-side after confirmation)
#     """
#     template_name = 'authentication/password_reset/password_reset_complete.html'
    
#     def get_context_data(self, **kwargs):
#         context = super().get_context_data(**kwargs)
#         context['tenant'] = getattr(self.request, 'tenant', None)
#         context['is_learning_portal'] = getattr(self.request, 'is_learning_portal', False)
#         context['login_url'] = reverse('account:login')
#         return context


# # =====================================
# # LEARNING PORTAL PASSWORD RESET (For learners/facilitators)
# # =======================================

# class LearnPasswordResetView(PasswordResetView):
# #     """
# #     Password reset for learning portal users (vendor=None).
    
# #     DIFFERENCE FROM TENANT RESET:
# #     - No tenant filtering
# #     - Only allows learner/facilitator roles
# #     """
# #     template_name = 'authentication/password_reset/password_reset_form.html'
# #     form_class = TenantPasswordResetForm
# #     success_url = reverse_lazy('account:password_reset_done')
# #     email_template_name = 'authentication/password_reset/password_reset_email.html'
    
# #     def dispatch(self, request, *args, **kwargs):
# #         """Ensure this is only accessible from learning portal."""
# #         if not getattr(request, 'is_learning_portal', False):
# #             messages.error(request, "This page is only accessible from the learning portal.")
# #             return redirect('account:login')
# #         return super().dispatch(request, *args, **kwargs)
    
# #     def get_form_kwargs(self):
# #         """Pass tenant=None for learning portal."""
# #         kwargs = super().get_form_kwargs()
# #         kwargs['tenant'] = None
# #         kwargs['is_learning_portal'] = True
# #         return kwargs


# # Admin-only vendor-admin creation
# def is_platform_admin(user):
#     return user.is_authenticated and user.is_platform_admin

# @user_passes_test(is_platform_admin)
# def create_vendor_admin(request, vendor_id):
#     vendor = get_object_or_404(Vendor, internal_id=vendor_id)
#     if request.method == 'POST':
#         form = RegistrationForm(request.POST)
#         if form.is_valid():
#             form.save(vendor=vendor, role='vendor_admin')
#             return redirect('admin:tenants_vendor_change', vendor.internal_id)
#     else:
#         form = RegistrationForm()
#     return render(request, 'registration/create_vendor_admin.html', {'form': form, 'vendor': vendor})




# apps/accounts/views.py

from django.shortcuts import render, redirect
from django.contrib import messages
from django.urls import reverse, reverse_lazy
from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.utils.encoding import force_bytes, force_str

from django.template.loader import render_to_string
from django.core.mail import send_mail
from django.contrib.sites.shortcuts import get_current_site

from ..forms import TenantPasswordResetForm


def tenant_password_reset_view(request):

    tenant = getattr(request, "tenant", None)

    if request.method == "POST":

        form = TenantPasswordResetForm(
            request.POST,
            tenant=tenant
        )

        if form.is_valid():

            email = form.cleaned_data["email"]
            users = form.get_users(email)

            print(f"\n--- RESET DEBUG: Found {len(users)} users for {email} ---")

            for user in users:

                token = default_token_generator.make_token(user)
                uid = urlsafe_base64_encode(force_bytes(user.pk))

                current_site = get_current_site(request)
                domain = current_site.domain
                protocol = "https" if request.is_secure() else "http"

                reset_url = f"{protocol}://{domain}{reverse('account:password_reset_confirm', kwargs={'uidb64': uid, 'token': token})}"

                print("\n" + "!" * 60)
                print(f"DEVELOPMENT RESET LINK FOR {user.email}:")
                print(reset_url)
                print("!" * 60 + "\n")

                context = {
                    "user": user,
                    "reset_url": reset_url,
                    "tenant": tenant,
                    "domain": domain,
                    "site_name": current_site.name,
                    "protocol": protocol,
                }

                subject = render_to_string(
                    "authentication/emails/password_reset_subject.txt",
                    context
                ).strip()

                message = render_to_string(
                    "authentication/emails/password_reset_email.html",
                    context
                )

                send_mail(
                    subject,
                    message,
                    settings.DEFAULT_FROM_EMAIL,
                    [user.email],
                    fail_silently=False,
                )

            return redirect("account:password_reset_done")

    else:
        form = TenantPasswordResetForm(tenant=tenant)

    return render(
        request,
        "authentication/password_reset/password_reset_form.html",
        {
            "form": form,
            "tenant": tenant,
        },
    )


def tenant_password_reset_done_view(request):

    context = {
        "tenant": getattr(request, "tenant", None),
        "is_learning_portal": getattr(request, "is_learning_portal", False),
    }

    return render(
        request,
        "authentication/password_reset/password_reset_done.html",
        context
    )


from django.contrib.auth import get_user_model
from django.utils.http import urlsafe_base64_decode
from django.contrib.auth.tokens import default_token_generator
from ..forms import TenantSetPasswordForm

User = get_user_model()


def tenant_password_reset_confirm_view(request, uidb64, token):

    tenant = getattr(request, "tenant", None)
    is_learning_portal = getattr(request, "is_learning_portal", False)

    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except Exception:
        user = None

    validlink = False

    if user and default_token_generator.check_token(user, token):
        validlink = True

        if request.method == "POST":
            form = TenantSetPasswordForm(user, request.POST)

            if form.is_valid():

                user = form.save()

                messages.success(
                    request,
                    "Your password has been reset successfully. You can now log in with your new password."
                )

                return redirect("account:password_reset_complete")

        else:
            form = TenantSetPasswordForm(user)

    else:
        form = None

    context = {
        "form": form,
        "validlink": validlink,
        "tenant": tenant,
        "is_learning_portal": is_learning_portal,
    }

    return render(
        request,
        "authentication/password_reset/password_reset_confirm.html",
        context,
    )

def tenant_password_reset_complete_view(request):

    context = {
        "tenant": getattr(request, "tenant", None),
        "is_learning_portal": getattr(request, "is_learning_portal", False),
        "login_url": reverse("account:login"),
    }

    return render(
        request,
        "authentication/password_reset/password_reset_complete.html",
        context,
    )