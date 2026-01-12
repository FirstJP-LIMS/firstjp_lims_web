# *******************
# Download TestRequest Form (WEASYPRINT VERSION)
# *******************
from django.template.loader import render_to_string
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
from django.db.models import Sum
from django.conf import settings
import weasyprint

from ..models import TestRequest, TestAssignment, TestResult
from ..utils import generate_barcode_base64


# Download Result
from django.conf import settings
from django.template.loader import render_to_string
from django.http import HttpResponse
from weasyprint import HTML
import tempfile
from django.core.mail import EmailMessage


# NOTE: The render_to_pdf utility function has been removed. 
# WeasyPrint is simple enough to use directly in the view.

@login_required
def download_test_request(request, pk=None, blank=False):
    """
    Download a filled or blank Test Request form as PDF using WeasyPrint...
    """
    vendor = getattr(request.user, "vendor", None)
    vendor_profile = getattr(vendor, "profile", None)
    
    # Handle missing logo gracefully
    if vendor_profile and not vendor_profile.logo:
        vendor_profile.logo = None

    if blank:
        # Blank form version
        context = {
            "vendor": vendor,
            "vendor_profile": vendor_profile,
            "blank": True,
        }
        filename = f"Blank_Test_Request_Form.pdf"
    else:
        # Filled form version
        test_request = get_object_or_404(TestRequest, pk=pk, vendor=vendor)

        requested_tests = test_request.requested_tests.select_related("assigned_department")
        samples = test_request.samples.all()
        total_cost = requested_tests.aggregate(total=Sum("price"))["total"] or 0.00
        payment_mode = getattr(test_request, "payment_mode", "Not Specified")

        # Generate barcode
        barcode_image = generate_barcode_base64(test_request.request_id)

        context = {
            "vendor": vendor,
            "vendor_profile": vendor_profile,
            "test_request": test_request,
            "requested_tests": requested_tests,
            "samples": samples,
            "total_cost": total_cost,
            "payment_mode": payment_mode,
            "barcode_image": barcode_image,
            "blank": False,
        }
        filename = f"TestRequest_{test_request.request_id}.pdf"

    # Render the HTML template to a string
    html_string = render_to_string("laboratory/requests/pdf_template.html", context)

    # Prepare the HttpResponse
    response = HttpResponse(content_type='application/pdf')
    # Use 'attachment' to force download, or 'inline' to open in browser tab first
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    # --- WEASYPRINT GENERATION ---
    
    # Determine the base URL so WeasyPrint can find local images (like media/static)
    # request.build_absolute_uri('/') gives you e.g., http://localhost:8000/ or https://yourdomain.com/
    base_url = request.build_absolute_uri('/')

    try:
        # Create the HTML object with base_url for asset resolution
        html_obj = weasyprint.HTML(string=html_string, base_url=base_url)
        
        # Write the PDF directly to the response object (which acts like a file)
        html_obj.write_pdf(target=response)
        
        return response
        
    except Exception as e:
        # Log the actual error in development so you can see it in the console
        print(f"WeasyPrint Error: {e}")
        # In production, you might want to log this properly and return a generic error page
        return HttpResponse(f"Error generating PDF: {e}", status=500)



@login_required
def export_assignments_csv(request):
    """
    Export filtered assignments to CSV.
    """
    import csv
    from django.http import HttpResponse
    from django.utils import timezone
    
    vendor = request.user.vendor
    
    # Get filtered assignments (reuse filter logic)
    assignments = TestAssignment.objects.filter(vendor=vendor).select_related(
        'lab_test', 'request__patient', 'instrument', 'department'
    )
    
    # Apply same filters as list view
    status_filter = request.GET.get('status', '')
    if status_filter:
        assignments = assignments.filter(status=status_filter)
    
    # Create CSV response
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="assignments_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'
    
    writer = csv.writer(response)
    writer.writerow([
        'Assignment ID',
        'Request ID',
        'Patient',
        'Test',
        'Sample',
        'Department',
        'Instrument',
        'Status',
        'Priority',
        'Created',
        'Queued',
        'Analyzed',
        'Verified'
    ])
    
    for assignment in assignments:
        writer.writerow([
            assignment.id,
            assignment.request.request_id,
            str(assignment.request.patient),
            assignment.lab_test.name,
            assignment.sample.sample_id,
            assignment.department.name,
            assignment.instrument.name if assignment.instrument else 'Not Assigned',
            assignment.get_status_display(),
            assignment.request.priority,
            assignment.created_at.strftime('%Y-%m-%d %H:%M'),
            assignment.queued_at.strftime('%Y-%m-%d %H:%M') if assignment.queued_at else '',
            assignment.analyzed_at.strftime('%Y-%m-%d %H:%M') if assignment.analyzed_at else '',
            assignment.verified_at.strftime('%Y-%m-%d %H:%M') if assignment.verified_at else '',
        ])
    
    return response



@login_required
def download_result_pdf(request, result_id):
    # Use the same select_related for speed and data access
    result = get_object_or_404(
        TestResult.objects.select_related(
            'assignment__lab_test',
            'assignment__request__patient',
            'assignment__request__ordering_clinician',
            'assignment__sample',
            'verified_by',
        ),
        id=result_id,
        assignment__vendor=request.user.vendor
    )

    # Fetch history just like your detail view does
    previous_results = TestResult.objects.filter(
        assignment__request__patient=result.assignment.request.patient,
        assignment__lab_test=result.assignment.lab_test,
        released=True
    ).exclude(id=result.id).order_by('-entered_at')[:3] # Show last 3 for trend

    context = {
        'result': result,
        'previous_results': previous_results,
        'clinician': result.assignment.request.ordering_clinician,
    }

    # Render HTML to string
    html_string = render_to_string('laboratory/result/result_pdf1.html', context)
    html = HTML(string=html_string, base_url=request.build_absolute_uri())
    
    # Generate PDF
    pdf = html.write_pdf()

    response = HttpResponse(pdf, content_type='application/pdf')
    filename = f"Result_{result.assignment.request.request_id}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    return response

