from google import genai
from google.genai import types
from django.conf import settings
import json
import logging

logger = logging.getLogger(__name__)

class AIResultInterpreter:
    def __init__(self):
        if not hasattr(settings, 'GEMINI_API_KEY') or not settings.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is missing in settings.")
        
        # New SDK uses the Client class
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        # self.model_id = "gemini-1.5-pro"
        self.model_id = "gemini-2.5-flash"

    def generate_interpretation(self, result_obj):
        try:
            test_name = result_obj.test.name
            val = result_obj.result_value
            unit = result_obj.units
            ref_range = result_obj.reference_range
            patient = result_obj.assignment.request.patient

            prompt = f"""
                You are a board-certified pathologist assisting in lab result interpretation.

                IMPORTANT RULES:
                - Do NOT diagnose diseases.
                - Do NOT prescribe medications.
                - Do NOT provide treatment plans.
                - Only interpret the laboratory result.
                - If result is normal, clearly state it.
                - Be medically accurate and conservative.

                Patient:
                Age: {patient.age}
                Sex: {patient.gender}

                Lab Result:
                Test: {test_name}
                Value: {val} {unit}
                Reference Range: {ref_range}

                Return your response strictly in this JSON format:

                {{
                "clinical_interpretation": "Short, professional explanation for doctors",
                "patient_summary": "Simple explanation for patient",
                "abnormal_flag": true/false,
                "follow_up_note": "General suggestion if abnormal, otherwise null"
                }}
            """

            # The new SDK call structure
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type='application/json', # New SDK supports forcing JSON output!
                )
            )

            if not response or not response.text:
                raise ValueError("Empty response from Gemini API.")

            # With 'application/json' config, cleaning markdown is usually unnecessary, 
            # but we'll keep a check just in case.
            raw_text = response.text.strip()
            
            data = json.loads(raw_text)
            data['model_used'] = self.model_id
            return data

        except Exception as e:
            logger.exception("AI Service Failure with new SDK")
            raise e


# import google.generativeai as genai
# from django.conf import settings
# import json
# import logging

# logger = logging.getLogger(__name__)

# class AIResultInterpreter:
#     def __init__(self):
#         if not hasattr(settings, 'GEMINI_API_KEY') or not settings.GEMINI_API_KEY:
#             raise ValueError("GEMINI_API_KEY is missing in settings.")
#         genai.configure(api_key=settings.GEMINI_API_KEY)
#         self.model = genai.GenerativeModel('gemini-1.5-pro')

#     def generate_interpretation(self, result_obj):
#         try:
#             test_name = result_obj.test.name
#             val = result_obj.result_value
#             unit = result_obj.units
#             ref_range = result_obj.reference_range
#             patient = result_obj.assignment.request.patient

#             prompt = f"""
#                 You are a board-certified pathologist assisting in lab result interpretation.

#                 IMPORTANT RULES:
#                 - Do NOT diagnose diseases.
#                 - Do NOT prescribe medications.
#                 - Do NOT provide treatment plans.
#                 - Only interpret the laboratory result.
#                 - If result is normal, clearly state it.
#                 - Be medically accurate and conservative.

#                 Patient:
#                 Age: {patient.age}
#                 Sex: {patient.gender}

#                 Lab Result:
#                 Test: {test_name}
#                 Value: {val} {unit}
#                 Reference Range: {ref_range}

#                 Return your response strictly in this JSON format:

#                 {{
#                 "clinical_interpretation": "Short, professional explanation for doctors",
#                 "patient_summary": "Simple explanation for patient",
#                 "abnormal_flag": true/false,
#                 "follow_up_note": "General suggestion if abnormal, otherwise null"
#                 }}
#                 """

#             response = self.model.generate_content(prompt)
            
#             if not response or not response.text:
#                 raise ValueError("Empty response from Gemini API.")

#             raw_text = response.text
            
#             # Clean Markdown if present
#             if "```json" in raw_text:
#                 raw_text = raw_text.split("```json")[1].split("```")[0].strip()
#             elif "```" in raw_text:
#                 raw_text = raw_text.split("```")[1].split("```")[0].strip()

#             data = json.loads(raw_text)
#             data['model_used'] = 'gemini-1.5-pro'
#             return data

#         except json.JSONDecodeError as e:
#             logger.error(f"AI JSON Error: {str(e)} | Raw Text: {response.text}")
#             raise ValueError(f"AI returned invalid JSON: {str(e)}")
#         except Exception as e:
#             logger.exception("AI Service Failure")
#             raise e



