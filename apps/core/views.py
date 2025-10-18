from django.shortcuts import render
from . models import CompanyInfo

# Create your views here.

def home(request):
    Information = CompanyInfo.objects.first()
    context = {
        'Info': Information
    }
    return render(request, 'core/index.html', context)
