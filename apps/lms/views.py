from django.shortcuts import render


def learning_landing_view(request):
    return render(request, "lms/index.html")

def lms_dashboard(request):
    return render(request, 'lms/dashboard.html')
