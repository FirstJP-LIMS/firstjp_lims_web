"""
4. Summary of the Final Flow
1. Patient logs in: They see their list of tests.

2. User Choice: If a result is "Released," a button says "Explain with AI."

3. Instant Generation: The AI interprets the result value against the reference range and patient age/sex.

4. Database Storage: The result is saved so the lab doesn't pay for the same API call twice.

5. Educational Display: The patient reads a friendly summary, but the technical data is tucked away for their actual doctor to see.
"""


# patient/views/ai_engine.py
from django.shortcuts import get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from labs.models import TestResult, AIInterpretation
from labs.services.ai_service import AIResultInterpreter


# patient/views/ai_engine.py

@login_required
def patient_trigger_interpretation(request, result_id):
    """
    Patient triggers AI interpretation. 
    Matches PatientUser -> Patient -> TestRequest path.
    """
    try:
        # Fetch patient instance via the profile
        patient = request.user.patient_profile.patient
    except AttributeError:
        messages.error(request, "Patient profile not found.")
        return redirect('account:login')

    # Security: Result must belong to the patient AND be released
    result = get_object_or_404(
        TestResult, 
        id=result_id, 
        assignment__request__patient=patient,
        released=True 
    )

    # Prevent double-spending on API
    if hasattr(result, 'ai_insight'):
        messages.info(request, "Interpretation already exists.")
        return redirect('patient:view_results', request_id=result.assignment.request.request_id)

    try:
        interpreter = AIResultInterpreter()
        ai_data = interpreter.generate_interpretation(result)

        # Create record with auto-approval
        AIInterpretation.objects.create(
            result=result,
            clinical_text=ai_data.get("clinical_interpretation"),
            patient_text=ai_data.get("patient_summary"),
            abnormal_flag=ai_data.get("abnormal_flag"),
            follow_up_note=ai_data.get("follow_up_note"),
            model_version=ai_data.get("model_used"),
            is_approved=True 
        )
        messages.success(request, "Insight generated! You can now view the simple explanation.")

    except Exception as e:
        # Standardize error logging
        logger.error(f"Patient AI Trigger Failed: {str(e)}")
        messages.error(request, "The AI interpreter is temporarily unavailable. Please try again later.")

    return redirect('patient:view_results', request_id=result.assignment.request.request_id)


