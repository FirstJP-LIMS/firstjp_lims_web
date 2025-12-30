from django.shortcuts import render
from . models import CompanyInfo

# Create your views here.

def platform_home(request):
    # Information = CompanyInfo.objects.first()
    Information = CompanyInfo.objects.all()
    context = {
        'Info': Information
    }
    return render(request, 'platform/pages/index.html', context)


# FIRSTJP DATA:     
def firstjp_index(request):
    return render(request, 'firstjp/index.html')

def firstjp_payments(request):
    return render(request, 'firstjp/payments.html')

def firstjp_admin(request):
    return render(request, 'firstjp/admin.html')