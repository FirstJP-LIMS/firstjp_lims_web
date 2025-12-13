┌─────────────────────────────────────────────────────────────┐
│                    TEST REQUEST CREATION                     │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  PATIENT PATHWAY                  CLINICIAN PATHWAY          │
│  ├─ Self-service                  ├─ Orders for patients    │
│  ├─ Limited test catalog          ├─ Full test catalog      │
│  ├─ May require payment upfront   ├─ Institutional billing  │
│  ├─ requested_by = patient_user   ├─ requested_by = clinician│
│  └─ ordering_clinician = NULL     └─ ordering_clinician = self│
│                                                              │
└─────────────────────────────────────────────────────────────┘