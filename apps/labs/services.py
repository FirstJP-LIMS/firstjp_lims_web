"""
Service layer for instrument communication.
Handles all external API calls to Windows LIMS.
"""
import requests
import logging
from typing import Optional, Dict, Any
from django.conf import settings
from django.utils import timezone
from .models import TestAssignment, TestResult, InstrumentLog, Equipment

logger = logging.getLogger(__name__)


class InstrumentAPIError(Exception):
    """Custom exception for instrument API errors"""
    pass


class InstrumentService:
    """Handles communication with laboratory instruments via Windows LIMS API"""
    
    def __init__(self, instrument: Equipment):
        self.instrument = instrument
        self.base_url = instrument.api_endpoint.rstrip('/')
        self.api_key = instrument.api_key
        self.timeout = getattr(settings, 'INSTRUMENT_API_TIMEOUT', 10)
    
    def _get_headers(self) -> Dict[str, str]:
        """Generate request headers with authentication"""
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }
        
        if self.api_key:
            # Adjust based on your Windows LIMS auth method
            headers['Authorization'] = f'Bearer {self.api_key}'
            # OR: headers['X-API-Key'] = self.api_key
        
        return headers
    
    def _log_communication(
        self, 
        assignment: TestAssignment, 
        log_type: str, 
        payload: Dict[str, Any], 
        response_code: Optional[int] = None,
        error_message: str = ""
    ):
        """Log all instrument communications"""
        InstrumentLog.objects.create(
            assignment=assignment,
            instrument=self.instrument,
            log_type=log_type,
            payload=payload,
            response_code=response_code,
            error_message=error_message
        )
    
    def send_test_to_instrument(self, assignment: TestAssignment) -> Dict[str, Any]:
        """
        Send test assignment to instrument queue.
        
        Returns:
            dict: Response from instrument including external_id
        """
        if not assignment.can_send_to_instrument():
            raise InstrumentAPIError("Assignment cannot be sent to instrument")
        
        # Build payload according to Windows LIMS specification
        payload = {
            "id": 0,  # Let Windows LIMS generate
            "patientId": assignment.request.patient.patient_id,
            "testName": assignment.lab_test.code,  # Use code for instrument
            "testCode": assignment.lab_test.code,
            "sampleId": assignment.sample.sample_id,
            "requestId": assignment.request.request_id,
            "priority": assignment.request.priority,
            "specimenType": assignment.lab_test.specimen_type,
            # Additional metadata
            "metadata": {
                "assignmentId": assignment.id,
                "vendorId": assignment.vendor.id,
                "departmentId": assignment.department.id,
            }
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/api/queue",
                json=payload,
                headers=self._get_headers(),
                timeout=self.timeout
            )
            
            response.raise_for_status()
            result = response.json()
            
            # Log success
            self._log_communication(
                assignment=assignment,
                log_type='send',
                payload=payload,
                response_code=response.status_code
            )
            
            # Update assignment
            external_id = result.get('id') or result.get('queueId')
            assignment.mark_queued(external_id=str(external_id) if external_id else None)
            assignment.last_sync_attempt = timezone.now()
            assignment.save(update_fields=['last_sync_attempt'])
            
            logger.info(f"Successfully sent assignment {assignment.id} to instrument {self.instrument.name}")
            return result
            
        except requests.exceptions.Timeout:
            error_msg = f"Timeout connecting to instrument {self.instrument.name}"
            logger.error(error_msg)
            self._log_communication(
                assignment=assignment,
                log_type='error',
                payload=payload,
                error_message=error_msg
            )
            assignment.retry_count += 1
            assignment.save(update_fields=['retry_count'])
            raise InstrumentAPIError(error_msg)
            
        except requests.exceptions.RequestException as e:
            error_msg = f"Error sending to instrument: {str(e)}"
            logger.error(error_msg)
            self._log_communication(
                assignment=assignment,
                log_type='error',
                payload=payload,
                response_code=getattr(e.response, 'status_code', None),
                error_message=error_msg
            )
            assignment.retry_count += 1
            assignment.save(update_fields=['retry_count'])
            raise InstrumentAPIError(error_msg)
    
    def fetch_result_from_instrument(self, assignment: TestAssignment) -> Optional[TestResult]:
        """
        Fetch completed result from instrument.
        
        Returns:
            TestResult: Created or updated result object
        """
        if not assignment.external_id:
            raise InstrumentAPIError("No external ID found for assignment")
        
        try:
            # Fetch by external_id
            response = requests.get(
                f"{self.base_url}/api/results/{assignment.external_id}",
                headers=self._get_headers(),
                timeout=self.timeout
            )
            
            response.raise_for_status()
            result_data = response.json()
            
            # Log receipt
            self._log_communication(
                assignment=assignment,
                log_type='receive',
                payload=result_data,
                response_code=response.status_code
            )
            
            # Check if result is ready
            if result_data.get('status') != 'completed':
                logger.info(f"Result not ready for assignment {assignment.id}. Status: {result_data.get('status')}")
                return None
            
            # Parse and save result
            result = self._parse_and_save_result(assignment, result_data)
            
            logger.info(f"Successfully fetched result for assignment {assignment.id}")
            return result
            
        except requests.exceptions.RequestException as e:
            error_msg = f"Error fetching result: {str(e)}"
            logger.error(error_msg)
            self._log_communication(
                assignment=assignment,
                log_type='error',
                payload={'external_id': assignment.external_id},
                response_code=getattr(e.response, 'status_code', None),
                error_message=error_msg
            )
            raise InstrumentAPIError(error_msg)
    
    def _parse_and_save_result(
        self, 
        assignment: TestAssignment, 
        result_data: Dict[str, Any]
    ) -> TestResult:
        """Parse instrument response and save result"""
        
        # Get or create result
        result, created = TestResult.objects.get_or_create(
            assignment=assignment,
            defaults={
                'data_source': 'instrument',
                'entered_by': None,  # System-generated
            }
        )
        
        # Update result fields
        result.result_value = str(result_data.get('value', ''))
        result.units = result_data.get('unit', '') or assignment.lab_test.default_units or ''
        
        # Set reference range from test definition
        if assignment.lab_test.min_reference_value and assignment.lab_test.max_reference_value:
            result.reference_range = (
                f"{assignment.lab_test.min_reference_value} - "
                f"{assignment.lab_test.max_reference_value}"
            )
        elif assignment.lab_test.default_reference_text:
            result.reference_range = assignment.lab_test.default_reference_text
        
        # Handle additional fields from instrument
        if 'remarks' in result_data:
            result.remarks = result_data['remarks']
        
        if 'qualityControl' in result_data:
            result.remarks += f"\n[QC: {result_data['qualityControl']}]"
        
        result.save()
        
        # Auto-flag the result
        result.auto_flag_result()
        
        # Update assignment status
        assignment.mark_analyzed()
        
        return result
    
    def check_instrument_status(self) -> Dict[str, Any]:
        """Check if instrument is online and operational"""
        try:
            response = requests.get(
                f"{self.base_url}/api/status",
                headers=self._get_headers(),
                timeout=5
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Instrument {self.instrument.name} status check failed: {e}")
            return {'status': 'offline', 'error': str(e)}


def send_assignment_to_instrument(assignment_id: int) -> Dict[str, Any]:
    """
    Convenience function to send assignment to instrument.
    Can be called from views or background tasks.
    """
    assignment = TestAssignment.objects.select_related(
        'instrument', 'lab_test', 'request__patient', 'sample'
    ).get(id=assignment_id)
    
    if not assignment.instrument:
        raise InstrumentAPIError("No instrument assigned to this test")
    
    service = InstrumentService(assignment.instrument)
    return service.send_test_to_instrument(assignment)


def fetch_assignment_result(assignment_id: int) -> Optional[TestResult]:
    """
    Convenience function to fetch result from instrument.
    Can be called from views or background tasks.
    """
    assignment = TestAssignment.objects.select_related(
        'instrument', 'lab_test'
    ).get(id=assignment_id)
    
    if not assignment.instrument:
        raise InstrumentAPIError("No instrument assigned to this test")
    
    service = InstrumentService(assignment.instrument)
    return service.fetch_result_from_instrument(assignment)


def bulk_fetch_pending_results(instrument: Equipment, max_count: int = 50) -> int:
    """
    Fetch multiple pending results from an instrument.
    Useful for scheduled tasks.
    
    Returns:
        int: Number of results fetched
    """
    # Get assignments that are queued or in progress
    assignments = TestAssignment.objects.filter(
        instrument=instrument,
        status__in=['Q', 'I'],
        external_id__isnull=False
    ).select_related('lab_test')[:max_count]
    
    service = InstrumentService(instrument)
    fetched_count = 0
    
    for assignment in assignments:
        try:
            result = service.fetch_result_from_instrument(assignment)
            if result:
                fetched_count += 1
        except InstrumentAPIError as e:
            logger.warning(f"Could not fetch result for assignment {assignment.id}: {e}")
            continue
    
    logger.info(f"Fetched {fetched_count} results from {instrument.name}")
    return fetched_count

    