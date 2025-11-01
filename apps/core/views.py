from django.shortcuts import render
from . models import CompanyInfo

# Create your views here.

def platform_home(request):
    Information = CompanyInfo.objects.first()
    context = {
        'Info': Information
    }
    return render(request, 'pages/index.html', context)
