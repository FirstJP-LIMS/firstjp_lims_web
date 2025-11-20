# apps/tenants/views.py
# from django.core.mail import send_mail
from django.shortcuts import render, redirect
from django.contrib import messages
from django.db import transaction
from django.urls import reverse
from .models import Vendor, VendorDomain
from .forms import VendorOnboardingForm
from apps.accounts.models import User, VendorProfile
# from django.conf import settings
from .utils import send_vendor_onboarding_emails


def vendor_onboarding_view(request):
    if request.method == "POST":
        form = VendorOnboardingForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    # 1. Create Vendor
                    vendor = Vendor.objects.create(
                        name=form.cleaned_data["name"],
                        contact_email=form.cleaned_data["admin_email"],
                        plan_type=form.cleaned_data["plan_type"],
                        is_active=False,  # Wait for approval
                    )

                    # 2. Create Vendor Admin User
                    user = User.objects.create_user(
                        email=form.cleaned_data["admin_email"],
                        password=form.cleaned_data["admin_password"],
                        first_name=form.cleaned_data["admin_first_name"],
                        last_name=form.cleaned_data["admin_last_name"],
                        vendor=vendor,
                        role='vendor_admin',
                        is_staff=True
                    )

                    # 3. Create Vendor Profile
                    VendorProfile.objects.create(
                        vendor=vendor,
                        contact_number=form.cleaned_data.get("contact_number"),
                        office_address=form.cleaned_data["office_street_address"],
                        office_city_state=form.cleaned_data["office_city_state"],
                        office_country=form.cleaned_data["office_country"],
                        office_zipcode=form.cleaned_data["office_zipcode"],
                    )

                messages.success(request, "Vendor onboarding request submitted successfully! We'll review your application and contact you soon.")
                
                # send email to the user and platform-admin
                send_vendor_onboarding_emails(vendor, user)

                return redirect(reverse("vendor_onboarding_success"))

            except Exception as e:
                messages.error(request, f"An error occurred during submission. Please try again. Error: {str(e)}")
        else:
            print("Form errors:", form.errors)
            print("Form non-field errors:", form.non_field_errors())
            messages.error(request, "Please correct the errors below.")
    else:
        form = VendorOnboardingForm()

    return render(request, "platform/onboarding/onboarding_form.html", {"form": form})


def vendor_onboarding_success(request):
    steps = [
        ["1", "Application Review", "Our team verifies your information"],
        ["2", "Environment Setup", "We configure your LIMS environment"],
        ["3", "Welcome Package", "Credentials and guides will be sent"],
        ["4", "Onboarding Session", "Meet with our implementation team"],
    ]

    return render(request, "platform/onboarding/onboarding_success.html", {"steps":steps})

