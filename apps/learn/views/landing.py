from django.shortcuts import render


def index_page(request):
    return render(request, "lms/index.html")

# def lms_dashboard(request):
#     return render(request, 'lms/dashboard.html')
