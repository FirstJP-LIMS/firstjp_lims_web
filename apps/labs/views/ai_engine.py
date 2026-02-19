# laboratory/views/ai_engine.py
from django.shortcuts import get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from ..models import TestResult, AIInterpretation
from ..services.ai_service import AIResultInterpreter
from ..decorators import require_capability



@login_required
def generate_ai_insight(request, result_id):
    """
    Triggers the Gemini API to generate a draft interpretation for a specific result.
    """
    result = get_object_or_404(TestResult, id=result_id)
    
    # 1. Governance check: Only the vendor who owns the test can trigger AI
    if result.assignment.vendor != request.user.vendor:
        messages.error(request, "Unauthorized access.")
        return redirect("labs:result_detail", result_id=result.id)

    # 2. Prevent duplicate API calls if already generated
    if hasattr(result, 'ai_insight'):
        messages.info(request, "AI Insight already exists for this result.")
        return redirect("labs:result_detail", result_id=result.id)

    try:
        # 3. Call the AI Service
        interpreter = AIResultInterpreter()
        ai_data = interpreter.generate_interpretation(result)

        # 4. Save to Database
        AIInterpretation.objects.create(
            result=result,
            clinical_text=ai_data.get("clinical_interpretation"),
            patient_text=ai_data.get("patient_summary"),
            abnormal_flag=ai_data.get("abnormal_flag"),
            follow_up_note=ai_data.get("follow_up_note"),
            model_version=ai_data.get("model_used", "gemini-1.5-pro")
        )
        
        messages.success(request, "AI interpretation draft generated successfully.")
    
    except Exception as e:
        error_msg = str(e)
        if "429" in error_msg:
            messages.error(request, "AI Quota reached. Please wait 60 seconds before trying again.")
        else:
            messages.error(request, f"AI Error: {error_msg}")
        # messages.error(request, f"AI Service Error: {str(e)}")

    return redirect("labs:result_detail", result_id=result.id)


@require_capability("can_verify_results")
@login_required
def approve_ai_insight(request, insight_id):
    """
    Allows a Pathologist to officially 'sign off' on the AI draft.
    """
    insight = get_object_or_404(AIInterpretation, id=insight_id)

    insight.is_approved = True
    insight.reviewed_by = request.user
    insight.save()

    messages.success(
        request,
        "AI Interpretation has been approved and added to the final report."
    )
    return redirect("labs:result_detail", result_id=insight.result.id)


# @require_capability("can_verify_results")
# @login_required
# def approve_ai_insight(request, insight_id):
#     # UUID lookup works now
#     insight = get_object_or_404(AIInterpretation, id=insight_id)

#     # Ownership check: Ensure the pathologist belongs to the same vendor as the result
#     if insight.result.assignment.vendor != request.user.vendor:
#         messages.error(request, "Unauthorized approval attempt.")
#         return redirect("labs:dashboard")

#     insight.is_approved = True
#     insight.reviewed_by = request.user
#     insight.reviewed_at = timezone.now() # Add this for clinical auditing
#     insight.save()

#     messages.success(
#         request, 
#         "AI Interpretation has been approved and added to the final report."
#     )
#     return redirect("labs:result_detail", result_id=insight.result.id)