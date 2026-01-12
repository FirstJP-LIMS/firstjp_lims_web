# apps/notifications/domain_events.py
from dataclasses import dataclass, field
from typing import Any, Dict
from uuid import uuid4
from datetime import datetime

@dataclass
class DomainEvent:
    """
    Represents a lightweight domain event emitted by LIMS core components.
    """
    event_type: str             # e.g., 'appointment_created', 'test_result_ready'
    payload: Dict[str, Any]     # event-specific data
    timestamp: datetime = field(default_factory=datetime.utcnow)
    id: str = field(default_factory=lambda: str(uuid4()))


# # from dataclasses import dataclass, field
# # from typing import Any, Dict
# # from uuid import uuid4
# # from datetime import datetime
# from django.dispatch import Signal

# @dataclass
# class DomainEvent:
#     event_type: str        # e.g., 'TEST_RESULT_READY'
#     recipient_id: int      # Who gets it
#     payload: Dict[str, Any]
#     urgent: bool = False
#     timestamp: datetime = field(default_factory=datetime.utcnow)
#     event_id: str = field(default_factory=lambda: str(uuid4()))

# # This is the single entry point for the whole LIMS
# # It only expects one argument: 'event' (which must be a DomainEvent instance)
# notification_bus = Signal()