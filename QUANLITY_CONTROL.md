# Quality Control Module - Laboratory Information Management System (LIMS)

## Table of Contents
1. [Executive Summary](#executive-summary)
2. [Regulatory Framework & Standards](#regulatory-framework--standards)
3. [Quality Control Fundamentals](#quality-control-fundamentals)
4. [System Architecture & Data Flow](#system-architecture--data-flow)
5. [Module Components & Endpoints](#module-components--endpoints)
6. [Standard Operating Procedures](#standard-operating-procedures)
7. [User Roles & Permissions](#user-roles--permissions)
8. [Compliance & Audit Trail](#compliance--audit-trail)
9. [Reporting & Analytics](#reporting--analytics)

---

## Executive Summary

### Purpose
The Quality Control (QC) module ensures the accuracy, precision, and reliability of laboratory test results by implementing systematic monitoring procedures compliant with international standards (ISO 15189, ISO 9001, CAP, CLIA).

### Key Features
- **QC Lot Management**: Track control materials with defined acceptable ranges
- **Daily QC Entry**: Record and validate quality control measurements
- **Westgard Rules Engine**: Automated detection of out-of-control conditions
- **Levey-Jennings Charts**: Visual trending and statistical process control
- **Corrective Action Tracking**: Document and resolve QC failures
- **Compliance Reporting**: Monthly performance metrics and sigma calculations

### Business Value
- Ensures patient safety through reliable test results
- Maintains regulatory compliance and accreditation
- Reduces manual errors and improves efficiency
- Provides data-driven decision making for quality improvement
- Creates comprehensive audit trails for inspections

---

## Regulatory Framework & Standards

### ISO 15189:2022 - Medical Laboratories Requirements

#### Key Requirements Addressed:

**Clause 7.4 - Quality Assurance of Examination Procedures**
- The laboratory shall design internal quality control systems that verify the attainment of the intended quality of results
- QC procedures shall be performed at defined intervals
- QC results shall be reviewed at planned intervals
- When QC rules are violated, corrective action shall be taken

**Clause 7.10 - Quality Control**
- Use control materials that react to the examining system in a manner similar to patient samples
- Monitor performance at intervals established on the basis of the stability of the procedure
- Statistical techniques shall be applied to review results and detect trends

**Clause 8.6 - Quality Indicators**
- Establish quality indicators to monitor and evaluate performance
- Include rejection rates due to QC failures
- Document corrective actions taken

### ISO 9001:2015 - Quality Management Systems

**Clause 8.5.1 - Control of Production and Service Provision**
- Implement suitable monitoring and measurement activities
- Maintain documented information to demonstrate conformity

**Clause 10.2 - Nonconformity and Corrective Action**
- Take action to control and correct nonconformities
- Evaluate the need for action to eliminate causes
- Retain documented information as evidence

### CLIA (Clinical Laboratory Improvement Amendments)

**42 CFR 493.1256 - Condition: Quality Control**
- Each specialty and subspecialty must include quality control
- Quality control procedures must monitor the accuracy and precision
- Corrective action must be taken and documented

### CAP (College of American Pathologists)

**GEN.40300 - Quality Control**
- QC must be performed each day of testing
- Control materials must be tested in the same manner as patient samples
- All QC data must be reviewed before reporting patient results

---

## Quality Control Fundamentals

### Statistical Process Control (SPC)

#### Control Limits
Quality control relies on establishing acceptable ranges based on statistical principles:

```
Mean (x̄): Target value for the QC material
Standard Deviation (SD/σ): Measure of variability

Control Limits:
- ±1 SD: 68.3% of values (acceptable variation)
- ±2 SD: 95.5% of values (warning zone)
- ±3 SD: 99.7% of values (action limit)
```

#### Westgard Rules
Multi-rule system for detecting systematic and random errors:

| Rule | Description | Interpretation |
|------|-------------|----------------|
| **1₂ₛ** | Single value exceeds ±2SD | Random error - acceptable run |
| **1₃ₛ** | Single value exceeds ±3SD | Random error - reject run |
| **2₂ₛ** | Two consecutive values exceed ±2SD (same side) | Systematic error - recalibrate |
| **R₄ₛ** | Range between consecutive values > 4SD | Random error - check precision |
| **4₁ₛ** | Four consecutive values exceed ±1SD (same side) | Systematic shift - investigate |
| **10x** | Ten consecutive values on same side of mean | Systematic bias - recalibrate |

### QC Material Levels

```
Level 1 (Low):    Tests low pathological range
Level 2 (Normal): Tests reference/normal range  
Level 3 (High):   Tests high pathological range
```

**Rationale**: Multi-level QC ensures accuracy across the entire analytical measurement range, detecting issues that might only affect specific concentration ranges.

---

## System Architecture & Data Flow

### Entity Relationship Diagram

```
┌─────────────┐
│   Vendor    │
└──────┬──────┘
       │
       ├──────────────────┐
       │                  │
       ▼                  ▼
┌─────────────┐    ┌─────────────┐
│ VendorTest  │    │  Equipment  │
└──────┬──────┘    └──────┬──────┘
       │                  │
       ▼                  │
┌─────────────┐           │
│   QCLot     │◄──────────┤
│  (Control   │           │
│  Material)  │           │
└──────┬──────┘           │
       │                  │
       ▼                  │
┌─────────────┐           │
│  QCResult   │◄──────────┘
│  (Daily     │
│   Entry)    │
└──────┬──────┘
       │
       ├──────────────────┐
       │                  │
       ▼                  ▼
┌─────────────┐    ┌─────────────┐
│  QCAction   │    │QCTestApproval│
│ (Corrective │    │   (Daily     │
│   Action)   │    │  Approval)   │
└─────────────┘    └─────────────┘
```

### Data Flow: Complete QC Workflow

```
START: Lab Opens for Day
        │
        ▼
┌────────────────────────────────┐
│ 1. SETUP PHASE                 │
│ - Check active QC lots         │
│ - Verify lot expiration        │
│ - Prepare control materials    │
└────────┬───────────────────────┘
         │
         ▼
┌────────────────────────────────┐
│ 2. QC ENTRY PHASE              │
│ Endpoint: qc_entry             │
│ - Technician runs controls     │
│ - Enters measured values       │
│ - System auto-calculates:      │
│   • Z-score                    │
│   • Status (PASS/WARNING/FAIL) │
│   • Run number                 │
└────────┬───────────────────────┘
         │
         ▼
┌────────────────────────────────┐
│ 3. VALIDATION PHASE            │
│ Model: QCResult.save()         │
│ - Compare to control limits    │
│ - Apply Westgard rules         │
│ - Check previous results       │
│ - Flag violations              │
└────────┬───────────────────────┘
         │
         ├─────── PASS ───────┐
         │                    │
         │                    ▼
         │            ┌─────────────────┐
         │            │ 4a. AUTO-APPROVE│
         │            │ - Mark approved │
         │            │ - Allow patient │
         │            │   testing       │
         │            └─────────────────┘
         │
         └─── FAIL/WARNING ──┐
                             │
                             ▼
                     ┌─────────────────────┐
                     │ 4b. CORRECTIVE      │
                     │     ACTION REQUIRED │
                     │ Endpoint:           │
                     │ qc_action_create    │
                     │ - Document problem  │
                     │ - Record action     │
                     │ - Repeat QC         │
                     └──────┬──────────────┘
                            │
                            ▼
                     ┌─────────────────────┐
                     │ 5. RESOLUTION       │
                     │ - Verify fix        │
                     │ - Close action      │
                     │ - Approve testing   │
                     └─────────────────────┘
```

### Technical Architecture

```
┌──────────────────────────────────────────────────────┐
│                  PRESENTATION LAYER                   │
│                                                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐          │
│  │Dashboard │  │QC Entry  │  │ Reports  │          │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘          │
└───────┼─────────────┼─────────────┼─────────────────┘
        │             │             │
┌───────┼─────────────┼─────────────┼─────────────────┐
│       │    APPLICATION LAYER      │                 │
│       ▼             ▼             ▼                 │
│  ┌────────────────────────────────────┐            │
│  │         Django Views Layer          │            │
│  │  - qc_dashboard                    │            │
│  │  - qc_entry_view                   │            │
│  │  - qc_results_list                 │            │
│  │  - levey_jennings_chart            │            │
│  │  - qc_action_create                │            │
│  └────────────┬───────────────────────┘            │
└───────────────┼────────────────────────────────────┘
                │
┌───────────────┼────────────────────────────────────┐
│               │      BUSINESS LOGIC LAYER          │
│               ▼                                     │
│  ┌────────────────────────────────────┐           │
│  │        Django Models Layer          │           │
│  │  - QCLot.save()                    │           │
│  │    • Auto-calculate limits         │           │
│  │    • Enforce one active lot        │           │
│  │  - QCResult.save()                 │           │
│  │    • Calculate z-score             │           │
│  │    • Determine status              │           │
│  │    • Apply Westgard rules          │           │
│  │  - QCAction tracking               │           │
│  └────────────┬───────────────────────┘           │
└───────────────┼────────────────────────────────────┘
                │
┌───────────────┼────────────────────────────────────┐
│               │       DATA LAYER                   │
│               ▼                                     │
│  ┌────────────────────────────────────┐           │
│  │     PostgreSQL Database            │           │
│  │  - QC Lots                         │           │
│  │  - QC Results                      │           │
│  │  - QC Actions                      │           │
│  │  - Audit Trails                    │           │
│  └────────────────────────────────────┘           │
└────────────────────────────────────────────────────┘
```

---

## Module Components & Endpoints

### 1. QC LOT MANAGEMENT

#### Purpose
Manage control material lots with defined target values and acceptable ranges. Each lot represents a batch of QC material (e.g., Bio-Rad Level 2 Glucose Control, Lot #ABC123).

#### Endpoints

##### **GET /qc/lots/** - `qclot_list`
**Purpose**: Display all QC lots for the laboratory

**User Story**: *"As a lab supervisor, I need to see all QC lots to monitor which are active and which are expiring soon."*

**Request Parameters**:
- `test` (optional): Filter by specific test
- `active` (optional): Filter by active status (true/false)

**Response Data**:
- List of QC lots with test information
- Status indicators (active/inactive/expired)
- Expiration dates and warnings

**Business Rules**:
- Only one lot per vendor/test/level can be active
- Expired lots automatically flagged
- Shows days until expiration for active lots

**Navigation From**:
- Main QC Dashboard
- QC Entry (when selecting lot)

**Navigation To**:
- Create new lot (`qclot_create`)
- Edit lot (`qclot_edit`)
- View chart (`levey_jennings_chart`)

---

##### **POST /qc/lots/create/** - `qclot_create`
**Purpose**: Create new QC lot with target values

**User Story**: *"As a lab supervisor, when we receive new QC material, I need to enter the lot number and target values from the manufacturer's certificate."*

**Required Fields**:
```python
{
    "test": ForeignKey,           # Which test (e.g., Glucose)
    "lot_number": "ABC12345",     # Manufacturer's lot number
    "level": "L2",                # Low/Normal/High
    "target_value": 100.0,        # Expected mean
    "sd": 5.0,                    # Standard deviation
    "units": "mg/dL",             # Units
    "expiry_date": "2025-12-31",  # Expiration
    "received_date": "2025-01-15" # Receipt date
}
```

**Auto-Calculated on Save**:
```python
mean = target_value
limit_1sd_low = target_value - (1 × sd)
limit_1sd_high = target_value + (1 × sd)
limit_2sd_low = target_value - (2 × sd)
limit_2sd_high = target_value + (2 × sd)
limit_3sd_low = target_value - (3 × sd)
limit_3sd_high = target_value + (3 × sd)
```

**Validation Rules**:
- Cannot activate expired lot
- Expiry date must be after received date
- Must provide either (target + SD) OR (explicit_low + explicit_high)
- Activating new lot auto-deactivates other lots for same test/level

**Success Flow**:
1. Form submitted
2. Model calculates control limits
3. Deactivates conflicting lots
4. Redirects to lot list
5. Shows success message

---

##### **POST /qc/lots/<pk>/toggle/** - `qclot_toggle_active`
**Purpose**: Activate or deactivate a QC lot

**User Story**: *"As a lab supervisor, when we open a new vial or finish an old one, I need to switch which lot is active."*

**Business Logic**:
```python
if activating:
    - Check not expired
    - Set is_active = True
    - Set opened_date = today
    - Auto-deactivate other lots (vendor/test/level)
    
if deactivating:
    - Set is_active = False
    - Set closed_date = today
```

**Use Cases**:
- Opening new QC vial
- Finishing current lot
- Temporarily suspending problematic lot
- Switching between lots

---

### 2. QC ENTRY & DAILY OPERATIONS

##### **POST /qc/entry/** - `qc_entry_view`
**Purpose**: Daily QC result entry by technicians

**User Story**: *"As a medical laboratory technician, every morning before patient testing, I run QC controls and enter the results to verify the analyzer is working properly."*

**Workflow**:
```
1. Technician selects active QC lot from dropdown
2. Runs control material on analyzer
3. Enters measured value
4. Optionally notes instrument used
5. Submits form
```

**Backend Processing** (QCResult.save()):
```python
# Auto-calculate run number
run_number = QCResult.objects.filter(
    vendor=vendor,
    qc_lot=lot,
    run_date=today
).count() + 1

# Calculate z-score
z_score = (result_value - lot.mean) / lot.sd

# Determine status
if result_value outside ±3SD:
    status = 'FAIL'
elif result_value outside ±2SD:
    status = 'WARNING'
else:
    status = 'PASS'

# Apply Westgard Rules
check_westgard_rules()  # Checks last 10 results

# Auto-approve if PASS
if status == 'PASS' and no violations:
    is_approved = True
    approved_at = now()
```

**Westgard Rules Implementation**:
```python
def check_westgard_rules(self):
    recent_results = last 10 results
    
    # Rule 1₃ₛ: Single value > ±3SD
    if |z_score| > 3:
        violation = "1₃ₛ: Out of control"
    
    # Rule 2₂ₛ: Two consecutive > ±2SD (same side)
    if (z[0] > 2 AND z[1] > 2) OR (z[0] < -2 AND z[1] < -2):
        violation = "2₂ₛ: Systematic error"
    
    # Rule R₄ₛ: Range > 4SD
    if |value[0] - value[1]| > 4×SD:
        violation = "R₄ₛ: Random error"
    
    # Rule 4₁ₛ: Four consecutive > ±1SD (same side)
    if all(z[0:4] > 1) OR all(z[0:4] < -1):
        violation = "4₁ₛ: Shift detected"
    
    # Rule 10x: Ten consecutive same side
    if all(z[0:10] > 0) OR all(z[0:10] < 0):
        violation = "10x: Trend detected"
```

**Decision Points**:
```
QC Result → Status?
    │
    ├─ PASS → Auto-approve → Allow patient testing ✓
    │
    ├─ WARNING → Manual review required → Supervisor decision
    │
    └─ FAIL → STOP → Corrective action required → Repeat QC
```

**Response After Save**:
- Shows result status with color coding
- Displays any Westgard rule violations
- Lists today's QC runs in table
- Provides quick link to view chart

---

##### **GET /qc/results/** - `qc_results_list`
**Purpose**: View and search all QC results

**User Story**: *"As a lab supervisor, I need to review all QC results to identify patterns and verify technicians are running QC properly."*

**Display Data**:
```python
For each result:
- Date and time
- Test name and level
- Result value with status badge
- Z-score
- Westgard violations (if any)
- Instrument used
- Technician who entered
- Approval status
```

**Summary Statistics**:
```python
Overall:
- Total runs
- Pass rate (%)
- Fail rate (%)
- Warning rate (%)
- Total violations
- Approval rate

Per Test:
- Test-specific metrics
- Pass/fail breakdown
- Recent trends
```

**Filters Available**:
- Date range
- Test type
- Status (PASS/WARNING/FAIL)
- Approved/pending
- Specific lot
- Instrument

**Actions**:
- Click row → View detail (`qc_result_detail`)
- View chart for lot
- Export to Excel (future)

---

##### **GET /qc/results/<pk>/** - `qc_result_detail`
**Purpose**: Detailed view of single QC result

**User Story**: *"As a lab supervisor investigating a QC failure, I need to see all details including what rules were violated and what corrective actions were taken."*

**Information Displayed**:
```python
Result Information:
- Full test name and level
- Lot number and target values
- Measured value vs. target
- Z-score calculation
- Status with visual indicator
- All control limits (1SD, 2SD, 3SD)

Context:
- Date/time of run
- Run number for the day
- Instrument used
- Technician who entered
- Comments entered

Quality Indicators:
- Westgard rules violated (if any)
- Rule explanations
- Historical context

Actions:
- Corrective actions taken (list)
- Resolution status
- Approval information
```

**Action Buttons**:
- **View Chart**: Links to `levey_jennings_chart` for this lot
- **Record Corrective Action**: Links to `qc_action_create` (if FAIL/WARNING)
- **Approve**: Manual approval (if WARNING and supervisor decides acceptable)
- **Edit**: Modify comments or information

**Related Data**:
- Previous 5 results for same lot
- Next 5 results after this one
- All corrective actions for this result

---

### 3. CORRECTIVE ACTIONS (CAPA)

##### **POST /qc/actions/create/<result_pk>/** - `qc_action_create`
**Purpose**: Document corrective action for failed QC

**User Story**: *"As a medical laboratory technician, when QC fails, I must document what I did to fix the problem before I can resume patient testing."*

**ISO 15189 Requirement**: Clause 7.10.3 - "When quality control rules are violated, the laboratory shall take corrective action"

**Action Types**:
```python
REPEAT      → Rerun QC with same lot
CALIBRATE   → Recalibrate analyzer
MAINTENANCE → Clean/maintain instrument
REAGENT     → Replace expired/defective reagent
NEW_LOT     → Open new QC lot
SERVICE     → Call service engineer
OTHER       → Describe custom action
```

**Required Fields**:
- Action type (dropdown)
- Detailed description (what exactly was done)
- Resolution status (resolved checkbox)
- Resolution notes (outcome after action)
- Performed by (auto-filled from current user)

**Workflow Example**:
```
1. QC fails (Glucose = 85 mg/dL, target = 100 ± 5)
2. Technician clicks "Record Corrective Action"
3. Selects action type: "CALIBRATE"
4. Describes: "Ran 2-point calibration using standards A and B. 
   Calibration passed with correlation r=0.998"
5. Checks "Resolved"
6. Notes: "Repeated QC after calibration. New result: 99 mg/dL - PASS"
7. Submits
8. Runs new QC to verify fix
```

**Business Rules**:
- Cannot be created for passing QC
- Must be created before patient testing resumes
- Links back to original failed QC result
- Timestamps action for audit trail

**Integration**:
- Updates original QCResult.corrective_action field
- Prevents patient testing until resolved
- Appears in QC result detail view
- Tracked in action list

---

##### **GET /qc/actions/** - `qc_action_list`
**Purpose**: View all corrective actions

**User Story**: *"As a quality manager, I need to review all corrective actions to identify recurring problems and improve processes."*

**Display Information**:
```python
For each action:
- Date/time performed
- Test and lot affected
- Action type
- Description summary
- Resolution status (✅ Resolved / ⏳ Pending)
- Performed by
- Days to resolution
```

**Filters**:
- Resolved/Pending status
- Action type
- Date range
- Test type
- Technician

**Statistics**:
- Total actions
- Resolved vs. pending
- Most common action types
- Average time to resolution
- Actions per month (trend)

**Quality Metrics**:
```python
Common Analysis Questions:
- Which tests fail most often?
- Which action types are most effective?
- Are failures increasing/decreasing?
- Which shifts have most QC issues?
- Is training needed for specific staff?
```

---

### 4. LEVEY-JENNINGS CHARTS

##### **GET /qc/chart/<qc_lot_id>/** - `levey_jennings_chart`
**Purpose**: Visual display of QC trends over time

**User Story**: *"As a lab supervisor, I need to see QC results plotted over time to detect trends, shifts, and systematic problems before they cause failures."*

**Chart Components**:
```
Y-axis: QC Result Value
X-axis: Date

Reference Lines:
- Mean (target value) - solid blue line
- +1SD, -1SD - dashed green lines
- +2SD, -2SD - dashed yellow lines
- +3SD, -3SD - dashed red lines (action limits)

Data Points:
- Green dots: PASS results
- Yellow dots: WARNING results
- Red dots: FAIL results
```

**Statistical Process Control Interpretation**:

```
Pattern Recognition:

1. Random Variation (Good):
   • Points scattered around mean
   • Roughly 68% within ±1SD
   • No patterns or trends
   → System in control

2. Shift (Problem):
   • All points suddenly higher/lower
   • Rule 4₁ₛ or 10x violation
   → Recalibrate instrument

3. Trend (Problem):
   • Gradual increase or decrease
   • Rule 10x violation
   → Reagent degradation, check expiry

4. Excessive Scatter (Problem):
   • Points very spread out
   • Rule R₄ₛ violation
   → Poor precision, maintenance needed

5. Bias (Problem):
   • Mean shifted from target
   • Points consistently high/low
   → Calibration drift
```

**Interactive Features**:
- Hover over point: See exact value, date, status
- Click point: Navigate to result detail
- Date range selector: 7/30/60/90 days
- Zoom and pan
- Export chart as image

**Data Endpoint**: Calls `levey_jennings_data` API

---

##### **GET /qc/chart/data/<qc_lot_id>/** - `levey_jennings_data`
**Purpose**: JSON API endpoint providing chart data

**Response Structure**:
```json
{
  "labels": ["11/01", "11/02", "11/03", ...],
  "datasets": [{
    "label": "QC Results",
    "data": [98.5, 101.2, 99.8, ...],
    "borderColor": "rgba(54, 162, 235, 1)",
    "pointBackgroundColor": ["green", "green", "red", ...]
  }],
  "control_limits": {
    "mean": 100.0,
    "sd_1_high": 105.0,
    "sd_1_low": 95.0,
    "sd_2_high": 110.0,
    "sd_2_low": 90.0,
    "sd_3_high": 115.0,
    "sd_3_low": 85.0
  },
  "lot_info": {
    "test": "Glucose",
    "level": "Level 2 - Normal",
    "lot_number": "ABC123",
    "target": 100.0,
    "units": "mg/dL"
  }
}
```

**Usage**: Frontend JavaScript fetches this data and renders Chart.js visualization

---

### 5. DASHBOARD & REPORTING

##### **GET /qc/dashboard/** - `qc_dashboard`
**Purpose**: Real-time overview of QC status

**User Story**: *"As a lab manager arriving at work, I need an at-a-glance view of which tests are approved for patient testing and which have QC problems."*

**Dashboard Layout**:

```
┌────────────────────────────────────────────────┐
│          TODAY'S QC STATUS                     │
│  Tests Approved: 12/15  Tests Failed: 2        │
│  Tests Pending: 1       Total Runs: 28         │
└────────────────────────────────────────────────┘

┌────────────────────────────────────────────────┐
│          QC STATUS BY TEST                     │
│                                                │
│  ✅ Glucose (L1, L2) - All Passed             │
│  ✅ HbA1c (L1, L2) - All Passed               │
│  ⏳ Creatinine (L2) - Pending                 │
│  ❌ Cholesterol (L1, L2) - L2 Failed          │
│     └─ Action: Recalibration in progress      │
│                                                │
└────────────────────────────────────────────────┘

┌────────────────────────────────────────────────┐
│          ALERTS & WARNINGS                     │
│  • 2 QC lots expiring in 7 days               │
│  • Cholesterol L2 failed - action pending     │
│  • Creatinine QC not run today                │
└────────────────────────────────────────────────┘

┌────────────────────────────────────────────────┐
│          RECENT FAILURES (Last 7 Days)         │
│  Date      Test         Level    Status        │
│  11/28     Cholesterol  L2       FAIL          │
│  11/25     HbA1c        L1       WARNING       │
└────────────────────────────────────────────────┘
```

**Color Coding**:
- 🟢 Green: All QC passed, approved for testing
- 🟡 Yellow: Warning or pending review
- 🔴 Red: Failed, testing NOT approved
- ⚪ Gray: Not run today

**Business Logic**:
```python
For each test:
1. Get all active lots for test
2. Check today's QC results
3. Determine test approval status:
   - All levels PASS → Approved ✅
   - Any level FAIL → Not Approved ❌
   - Not run yet → Pending ⏳
4. Highlight action required
```

**Quick Actions**:
- Click test → View results/chart
- Click warning → See details
- "Enter QC" button → Quick entry
- "View All Results" → Results list

---

##### **GET /qc/monthly/** - `qc_monthly_report`
**Purpose**: Monthly performance metrics and compliance reporting

**User Story**: *"As a quality manager, I need monthly QC statistics for accreditation reports, management review, and continuous improvement."*

**Report Structure**:

```
═══════════════════════════════════════════
    MONTHLY QC PERFORMANCE REPORT
    November 2025
═══════════════════════════════════════════

OVERALL METRICS
───────────────────────────────────────────
Total QC Runs:        420
Passed:               395 (94.0%)
Warnings:             18  (4.3%)
Failed:               7   (1.7%)
Overall Sigma:        5.64

PERFORMANCE BY TEST
───────────────────────────────────────────
Test         Runs  Pass%  Warn%  Fail%  Sigma
─────────────────────────────────────────── 
Glucose      45    97.8   2.2    0.0    5.87
HbA1c        42    95.2   2.4    2.4    5.71
Cholesterol  38    89.5   7.9    2.6    5.37
Creatinine   40    92.5   5.0    2.5    5.55
───────────────────────────────────────────
