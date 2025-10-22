# apps/tenants/views.py
from django.core.mail import send_mail
from django.shortcuts import render, redirect
from django.contrib import messages
from django.db import transaction
from django.urls import reverse
from .models import Vendor, VendorDomain
from .forms import VendorOnboardingForm
from apps.accounts.models import User
from django.conf import settings

def vendor_onboarding_view(request):
    """Handles self-registration, creating Vendor, Domain, and initial User."""
    if request.method == "POST":
        form = VendorOnboardingForm(request.POST)
        contact_email = request.POST.get("admin_email") # For notification emails
        if form.is_valid():
            # Use a transaction to ensure all 3 steps (Vendor, Domain, User) succeed or fail together.
            try:
                with transaction.atomic():
                    # 1. Create Vendor (Inactive)
                    vendor = Vendor.objects.create(
                        tenant_id=form.cleaned_data["tenant_id"],
                        name=form.cleaned_data["name"],
                        # Use admin email as vendor contact email
                        contact_email=form.cleaned_data["admin_email"],
                        # subdomain_prefix=form.cleaned_data["domain_name"],
                        plan_type=form.cleaned_data["plan_type"],
                        is_active=False, # Wait for Platform Admin approval
                    )

                    # # 2. Save Preferred Domain (if provided)
                    # preferred_domain = form.cleaned_data.get("domain_name")
                    # if preferred_domain:
                    #     VendorDomain.objects.create(
                    #         vendor=vendor,
                    #         domain_name=preferred_domain.lower(),
                    #         is_primary=True,
                    #     )

                    # 3. Create Vendor Admin User
                    User.objects.create_user(
                        email=form.cleaned_data["admin_email"],
                        password=form.cleaned_data["admin_password"],
                        first_name=form.cleaned_data["admin_first_name"],
                        last_name=form.cleaned_data["admin_last_name"],
                        vendor=vendor, # <-- Link to the new vendor
                        role='vendor_admin', # <-- Set the role
                        is_staff=True # Vendor Admins usually have some staff privileges
                    )

                #     # ✅ Notify platform admin
                #     send_mail(
                #         subject="🆕 New Vendor Onboarding Request",
                #         message=(
                #             f"A new vendor has requested onboarding:\n\n"
                #             f"Vendor Name: {vendor.name}\n"
                #             f"Tenant ID: {vendor.tenant_id}\n"
                #             f"Contact Email: {vendor.contact_email}\n"
                #             f"Preferred Domain: {preferred_domain or 'Not specified'}\n\n"
                #             f"Please review and proceed with domain setup."
                #         ),
                #         from_email=settings.DEFAULT_FROM_EMAIL,
                #         recipient_list=[settings.PLATFORM_ADMIN_EMAIL],
                #         fail_silently=True,
                #     )

                #     # ✅ Notify vendor admin (acknowledgment)
                #     send_mail(
                #         subject="Your Onboarding Request Received",
                #         message=(
                #             f"Dear {form.cleaned_data['admin_first_name']},\n\n"
                #             f"Thank you for registering {vendor.name}.\n"
                #             f"Our platform admin will contact you shortly to complete your domain setup.\n\n"
                #             f"Best Regards,\nThe LIS Platform Team"
                #         ),
                #         from_email=settings.DEFAULT_FROM_EMAIL,
                #         recipient_list=[contact_email],
                #         fail_silently=True,
                #     )
                # # If successful, commit transaction and send message
                messages.success(request, "Request submitted! We've sent an email to complete setup.")
                # Email notification logic here...
                return redirect(reverse("vendor_onboarding_success"))

            except Exception as e:
                # If anything in the atomic block fails, it rolls back. Log the error.
                messages.error(request, f"An error occurred during submission. Please try again. ({e})")
                # Log the exception (recommended)
                return redirect(reverse("vendor_onboarding"))

        else:
            messages.error(request, "Please correct the form errors.")
    else:
        form = VendorOnboardingForm()
        
    return render(request, "core/vendor_onboarding.html", {"form": form})

