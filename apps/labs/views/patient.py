from django.views.generic import ListView, DetailView
from django.db.models import Q
from ..models import Patient
from apps.appointment.models import Appointment


class PatientListView(ListView):
    model = Patient
    template_name = 'laboratory/patient/patient_list.html'
    context_object_name = 'patients'
    paginate_by = 25  # Critical for LIMS with thousands of records

    def get_queryset(self):
        # Ensure we only show patients belonging to the logged-in vendor staff
        queryset = Patient.objects.filter(vendor=self.request.user.vendor)
        
        # Simple Search Implementation
        query = self.request.GET.get('q')
        if query:
            queryset = queryset.filter(
                Q(first_name__icontains=query) | 
                Q(last_name__icontains=query) |
                Q(patient_id__icontains=query) |
                Q(contact_phone__icontains=query)
            )
        return queryset

# <script>
#     tailwind.config = {
#         theme: {
#             extend: {
#                 colors: {
#                     'navy': '#001f40',
#                     'medvuno-red': '#cc0033',
#                     'medvuno-gold': '#d4af37',
#                 }
#             }
#         }
#     }
# </script>

class PatientDetailView(DetailView):
    model = Patient
    template_name = 'laboratory/patient/patient_detail.html'
    context_object_name = 'patient'

    def get_queryset(self):
        # Multi-tenant security check
        return Patient.objects.filter(vendor=self.request.user.vendor)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Fetch latest 5 appointments
        context['recent_appointments'] = self.object.appointments.all().order_by('-slot__date')[:5]
        # Count stats for the dashboard cards
        context['total_appointments'] = self.object.appointments.count()
        return context