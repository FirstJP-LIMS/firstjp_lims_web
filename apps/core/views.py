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
