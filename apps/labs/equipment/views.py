# ------------------------------
# VENDOR OPERATIONS
# ------------------------------
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
from labs.models import Equipment, Department, AuditLog


@login_required
def equipment_list(request):
    """List all equipment for current vendor"""
    equipment = Equipment.objects.filter(
        vendor=request.user.vendor
    ).select_related('department').order_by('-status', 'name')
    
    context = {
        'equipment_list': equipment,
        'active_count': equipment.filter(status='active').count(),
        'maintenance_count': equipment.filter(status='maintenance').count(),
    }
    
    return render(request, 'laboratory/equipment/equipment_list.html', context)


# app_name/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.db import transaction
# from .models import Equipment, Department, AuditLog
from .forms import EquipmentForm


@login_required
@require_http_methods(["GET", "POST"])
def equipment_create(request):
    form = EquipmentForm(request.POST or None, vendor=request.user.vendor)

    if request.method == "POST":
        if form.is_valid():
            try:
                with transaction.atomic():
                    equipment = form.save(commit=False)
                    equipment.vendor = request.user.vendor
                    equipment.status = "active"
                    equipment.save()

                    # Log audit
                    AuditLog.objects.create(
                        vendor=request.user.vendor,
                        user=request.user,
                        action=f"Created equipment: {equipment.name} ({equipment.serial_number})",
                        ip_address=request.META.get("REMOTE_ADDR")
                    )

                messages.success(request, f"Equipment '{equipment.name}' created successfully.")
                return redirect("equipment_detail", equipment_id=equipment.id)

            except Exception as e:
                messages.error(request, f"Error creating equipment: {str(e)}")

        else:
            messages.error(request, "Please correct the errors below.")
    return render(request, "laboratory/equipment/equipment_form.html", {
        "form": form,
        "action": "Create"
    })


@login_required
def equipment_detail(request, equipment_id):
    """View equipment details and recent assignments"""
    equipment = get_object_or_404(
        Equipment.objects.select_related('department'),
        id=equipment_id,
        vendor=request.user.vendor
    )
    
    # Get recent assignments using this equipment
    recent_assignments = equipment.assignments.select_related(
        'request__patient',
        'lab_test'
    ).order_by('-created_at')[:10]
    
    # Get basic stats
    total_assignments = equipment.assignments.count()
    pending_assignments = equipment.assignments.filter(status='P').count()
    queued_assignments = equipment.assignments.filter(status='Q').count()
    
    context = {
        'equipment': equipment,
        'recent_assignments': recent_assignments,
        'total_assignments': total_assignments,
        'pending_assignments': pending_assignments,
        'queued_assignments': queued_assignments,
        'is_configured': bool(equipment.api_endpoint),
    }
    
    return render(request, 'laboratory/equipment/equipment_detail.html', context)


@login_required
@require_http_methods(["GET", "POST"])
def equipment_update(request, equipment_id):
    """Update equipment configuration"""
    equipment = get_object_or_404(
        Equipment,
        id=equipment_id,
        vendor=request.user.vendor
    )
    
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        model = request.POST.get("model", "").strip()
        department_id = request.POST.get("department")
        api_endpoint = request.POST.get("api_endpoint", "").strip()
        api_key = request.POST.get("api_key", "").strip()
        supports_auto_fetch = request.POST.get("supports_auto_fetch") == "on"
        status = request.POST.get("status")
        
        # Validation
        if not all([name, model, department_id, status]):
            messages.error(request, "Please fill in all required fields.")
            return redirect('account:equipment_update', equipment_id=equipment.id)
        
        try:
            department = Department.objects.get(
                id=department_id,
                vendor=request.user.vendor
            )
            
            # Track what changed
            changes = []
            if equipment.name != name:
                changes.append(f"name: '{equipment.name}' → '{name}'")
            if equipment.api_endpoint != api_endpoint:
                changes.append("API endpoint updated")
            if equipment.status != status:
                changes.append(f"status: {equipment.get_status_display()} → {dict(Equipment.EQUIPMENT_STATUS)[status]}")
            
            # Update equipment
            equipment.name = name
            equipment.model = model
            equipment.department = department
            equipment.api_endpoint = api_endpoint
            equipment.supports_auto_fetch = supports_auto_fetch
            equipment.status = status
            
            # Only update API key if provided (don't overwrite with blank)
            if api_key:
                equipment.api_key = api_key
            
            equipment.save()
            
            # Log the changes
            if changes:
                AuditLog.objects.create(
                    vendor=request.user.vendor,
                    user=request.user,
                    action=f"Updated equipment {equipment.name}: {', '.join(changes)}",
                    ip_address=request.META.get('REMOTE_ADDR')
                )
            
            messages.success(request, "Equipment updated successfully.")
            return redirect('account:equipment_detail', equipment_id=equipment.id)
            
        except Department.DoesNotExist:
            messages.error(request, "Invalid department selected.")
        except Exception as e:
            messages.error(request, f"Error updating equipment: {str(e)}")
    
    # GET request
    departments = Department.objects.filter(vendor=request.user.vendor)
    
    return render(request, 'laboratory/equipment/equipment_form.html', {
        'equipment': equipment,
        'departments': departments,
        'action': 'Update'
    })


@login_required
@require_http_methods(["POST"])
def equipment_calibrate(request, equipment_id):
    """Mark equipment as calibrated"""
    equipment = get_object_or_404(
        Equipment,
        id=equipment_id,
        vendor=request.user.vendor
    )
    
    from django.utils import timezone
    
    equipment.last_calibrated = timezone.now().date()
    equipment.save(update_fields=['last_calibrated'])
    
    AuditLog.objects.create(
        vendor=request.user.vendor,
        user=request.user,
        action=f"Calibrated equipment: {equipment.name}",
        ip_address=request.META.get('REMOTE_ADDR')
    )
    
    messages.success(request, f"Equipment '{equipment.name}' marked as calibrated.")
    return redirect('account:equipment_detail', equipment_id=equipment.id)


@login_required
@require_http_methods(["POST"])
def equipment_deactivate(request, equipment_id):
    """Deactivate or reactivate equipment"""
    equipment = get_object_or_404(
        Equipment,
        id=equipment_id,
        vendor=request.user.vendor
    )
    
    new_status = 'inactive' if equipment.status == 'active' else 'active'
    equipment.status = new_status
    equipment.save(update_fields=['status'])
    
    AuditLog.objects.create(
        vendor=request.user.vendor,
        user=request.user,
        action=f"Changed equipment {equipment.name} status to {new_status}",
        ip_address=request.META.get('REMOTE_ADDR')
    )
    
    messages.success(request, f"Equipment status changed to {equipment.get_status_display()}.")
    return redirect('account:equipment_detail', equipment_id=equipment.id)


@login_required
def equipment_test_connection(request, equipment_id):
    """Test API connection to equipment (AJAX endpoint)"""
    equipment = get_object_or_404(
        Equipment,
        id=equipment_id,
        vendor=request.user.vendor
    )
    
    if not equipment.api_endpoint:
        return JsonResponse({
            'success': False,
            'message': 'No API endpoint configured'
        })
    
    # Import your instrument service
    from app.labs.services import InstrumentService
    
    try:
        service = InstrumentService(equipment)
        status = service.check_instrument_status()
        
        return JsonResponse({
            'success': status.get('is_online', False),
            'message': status.get('message', 'Connection test completed'),
            'details': status
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Connection failed: {str(e)}'
        })
    
