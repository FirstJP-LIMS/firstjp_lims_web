from django.shortcuts import render


def index_page(request):
    return render(request, "learn/index.html")

# def lms_dashboard(request):
#     return render(request, 'lms/dashboard.html')
