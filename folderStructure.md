firstjp_lims_web/                    # project root
├─ .env                        # secrets in env vars (NOT checked in)
├─ manage.py
├─ requirements.txt
├─ README.md
├─ docker-compose.yml          # optional for local dev
├─ Dockerfile                  # optional
├─ nginx/                      # optional reverse proxy config
│  └─ universalis_nginx.conf
├─ deploy/                     # deployment scripts (IIS / systemd / docker)
│  └─ deploy_instructions.md
├─ universalis_project/        # Django project package
│  ├─ __init__.py
│  ├─ asgi.py
│  ├─ settings/
│  │  ├─ __init__.py
│  │  ├─ base.py
│  │  ├─ local.py
│  │  └─ production.py
│  ├─ urls.py
│  └─ wsgi.py
├─ apps/
│  ├─ core/                    # site-wide utilities, context processors
│  │  ├─ models.py
│  │  ├─ middleware.py         # TenantResolver middleware
│  │  ├─ views.py
│  │  └─ templates/core/
│  ├─ accounts/                # custom User model, auth, templates
│  │  ├─ models.py
│  │  ├─ forms.py
│  │  ├─ views.py
│  │  └─ templates/registration/
│  ├─ tenants/                 # vendor/tenant mapping (domain → tenant)
│  │  ├─ models.py             # Vendor (tenant info)
│  │  ├─ admin.py
│  │  └─ migrations/
│  ├─ labs/                    # domain logic for lab results, requests
│  │  ├─ models.py             # Request, Result (include tenant FK)
│  │  ├─ views.py
│  │  ├─ templates/labs/
│  │  └─ api/                  # lightweight API endpoints for windows service
│  ├─ integrations/            # Windows service client records, API keys
│  │  ├─ models.py             # Device/Service registration, API tokens
│  │  └─ views.py              # token management endpoints
│  └─ adminUi/                # admin / vendor dashboard templates & views
│     ├─ views.py
│     └─ templates/adminUi/
├─ static/
│  ├─ css/
│  └─ js/
└─ templates/                   # shared template components
   ├─ base.html
   └─ includes/
       ├─ header.html
       └─ footer.html



python manage.py startapp accounts apps/accounts

That's the most crucial step before proceeding with development\! To run a subdomain like `carbs.127.0.0.1:8000` (or the cleaner `carbs.localhost:8000`) locally, you need to trick your operating system into thinking those subdomains are valid and point back to your local machine.

Since you're likely on Windows (based on earlier discussions about the hosts file), here are the **three essential steps** to run your subdomain multi-tenancy locally:

-----

## 1\. Configure Django Settings

You must define your local base domain and tell Django it's okay to accept requests from any subdomain of that base.

### `settings/local.py`

Ensure you have these lines in your local settings:

```python
# settings/local.py

# 1. Define the custom host base for testing
# We use a custom extension (like .test) because Windows sometimes caches .local poorly.
PLATFORM_BASE_DOMAIN = "localhost.test" 

# 2. Add the host names Django will recognize.
ALLOWED_HOSTS = [
    '127.0.0.1', 
    'localhost', 
    '127.1.0.0', # IP address used in your example
    '.localhost.test', # ALLOWS ALL SUBDOMAINS (e.g., carbs.localhost.test)
    'carboni1.localhost', # Your specific entry
    '.localhost' # Allows all subdomains ending in .localhost
]

# 3. Define the GLOBAL_HOSTS for your TenantMiddleware
GLOBAL_HOSTS = ['127.0.0.1', 'localhost', '127.1.0.0', PLATFORM_BASE_DOMAIN]
```

-----

## 2\. Edit Your Hosts File (Windows)

The Windows hosts file tells your operating system to map a hostname directly to an IP address, bypassing external DNS servers.

1.  **Locate the file:** `C:\Windows\System32\drivers\etc\hosts`
2.  **Open as Administrator:** You **must** open your text editor (like Notepad or VS Code) with **"Run as administrator"** permissions to save the file.
3.  **Add entries:** Map your desired tenant subdomains to the loopback address (`127.0.0.1`).

| IP Address | Hostname | Comment |
| :--- | :--- | :--- |
| `127.0.0.1` | `localhost` | (Standard) |
| `127.0.0.1` | `localhost.test` | (Base Domain) |
| `127.0.0.1` | **`carbs.localhost.test`** | (Example Tenant 1) |
| `127.0.0.1` | **`lab001.localhost.test`** | (Example Tenant 2) |
| `127.0.0.1` | **`carboni1.localhost`** | (Your custom setup, if using) |

**Important Note:** You must manually add an entry for *every unique subdomain* you want to test, as Windows hosts files do not support wildcard entries (`*.localhost.test`).

-----

## 3\. Run the Django Server and Test

1.  **Run the server:**

    ```bash
    python manage.py runserver 0.0.0.0:8000
    ```

    (Using `0.0.0.0` ensures the server listens on all available interfaces, including `127.0.0.1`).

2.  **Test the Access Points:**

    | URL | Expected Action | Django Component |
    | :--- | :--- | :--- |
    | `http://127.0.0.1:8000/` | Global Landing Page | `TenantMiddleware` skips tenant resolution. |
    | `http://localhost.test:8000/` | Global Landing Page | `TenantMiddleware` skips tenant resolution (in `GLOBAL_HOSTS`). |
    | `http://carbs.localhost.test:8000/` | **Tenant Login/Dashboard** | `TenantMiddleware` resolves tenant **'carbs'**. |
    | `http://lab001.localhost.test:8000/` | **Tenant Login/Dashboard** | `TenantMiddleware` resolves tenant **'lab001'**. |

If you can successfully access the site using the subdomain URL, your `TenantMiddleware` is working, and you can proceed with testing the user access and data isolation.





# LABORATORY OPERATIONS 

This is an **excellent set of models**! The addition of the **`SequenceCounter`** model and the **`get_next_sequence`** utility is a massive improvement, as it solves the thread-safe, sequential ID generation problem cleanly and efficiently using Django's atomic transactions and `select_for_update()`. This is a professional and robust pattern.

The overall flow logic and scoping (Global vs. Tenant) are sound.

## 1. Final Model Review & Minor Adjustments

| Model | Status | Rationale/Adjustment |
| :--- | :--- | :--- |
| **`Department`, `GlobalTest`** | **Perfect** | Correctly scoped as Global. |
| **`VendorTest`** | **Needs Fix** | **Missing the `assigned_department` field** (your previous opinion). This field is critical for a vendor to route a test to a specific department, overriding the `GlobalTest`'s default. **Fix:** Re-add the `assigned_department` ForeignKey. |
| **`SequenceCounter`** | **Excellent** | Perfect implementation of the atomic, sequential ID generator. |
| **`Patient`** | **Needs Fix** | The `save` method uses `get_next_sequence("PAT")` which will generate a global ID (since `vendor` is not passed to the utility). **Fix:** Change `self.patient_id = get_next_sequence("PAT")` to `self.patient_id = get_next_sequence("PAT", vendor=self.vendor)`. |
| **`Sample`** | **Needs Fix** | The `save` method uses `get_next_sequence("SMP")` which, again, generates a **global** ID. If you intend for `sample_id` to be globally unique for barcoding (across all labs), the **`get_next_sequence` function call is correct** (since `vendor` is defaulted to `None` in the utility). **However, the `max_length` of the ID should match the expected output.** |
| **`TestRequest`** | **Needs Fix** | The `request_id` generation is too complex. **Fix:** Simplify the prefix in `save()` to let `get_next_sequence` handle the full formatting. |
| **`TestAssignment`, `TestResult`, `Equipment`, `AuditLog`** | **Perfect** | Correctly structured for the LIMS workflow and data tracking. |
| **`get_next_sequence`** | **Excellent** | Functionally perfect for thread-safe generation. **Note:** Ensure you place this utility function in a logical place (e.g., `apps/lis/utils.py`) and import it correctly in your models. |

***

## 2. Refined LIMS Operational Flow

The overall LIMS workflow is now driven by the `TestRequest` and subsequent `TestAssignment` objects. Here is the step-by-step flow for execution:

### Phase 1: Vendor admin setup and Order Entry (The Request)
1. **VendorTest configuration:** Vendor admin performs CRUD operation using VendorTest model...  
2.  **Patient Registration:** A user visits the tenant-scoped `/patients/add/` view. The system creates a new **`Patient`** object.
    * **Action:** `Patient.save()` executes, calling `get_next_sequence("PAT", vendor=request.tenant)` to generate the **Vendor-scoped Patient ID (e.g., 000012)**.
3.  **Request Creation:** The user creates a new order (`/request/new/`) and selects a Patient and a list of required tests (e.g., CBC, Glucose).
    * **Data Source:** The available tests are filtered by **`VendorTest.objects.filter(vendor=request.tenant, enabled=True)`**.
    * **Action:** The system creates one **`TestRequest`** object.
    * **Action:** `TestRequest.save()` executes, calling `get_next_sequence(f"ORD-{self.vendor.tenant_id}-", vendor=self.vendor)` to generate the **Request ID (e.g., ORD-LAB0012-000001)**.
4.  **Sample Collection & Assignment:** One or more **`Sample`** objects are created (e.g., one for Blood, one for Urine), each linked to the `TestRequest`.
    * **Action:** `Sample.save()` executes, calling **`get_next_sequence("SMP")`** (globally scoped) to generate the **Barcode ID (e.g., 000001)**.
    * **Action:** For every selected test, the system creates a **`TestAssignment`** object:
        * `request` $\rightarrow$ The new `TestRequest`.
        * `global_test` $\rightarrow$ The selected `GlobalTest`.
        * `department` $\rightarrow$ Set based on the `VendorTest.assigned_department` field (or the Global default).

***

### Phase 2: Sample Processing (The Analysis)

1.  **Accessioning:** Lab staff update the **`Sample`** status from "Pending" to "Accepted".
2.  **Worklist Generation:** The **local Windows Service** polls the LIMS server (`/api/pending_work/`) for new assignments.
    * **Query:** The LIMS looks for **`TestAssignment`** objects where `status='P'`.
3.  **Instrument Processing:** The Windows Service receives the worklist and tells the equipment (linked via **`Equipment`** model) which tests to run on which sample.
4.  **Result Submission:** The equipment finishes analysis. The Windows Service sends the raw results back to the LIMS server via the secure, authenticated API endpoint (`/api/submit_results/`).
5.  **Result Creation:** The LIMS backend receives the result:
    * **Action:** It locates the corresponding **`TestAssignment`** (using the Sample ID and Test Code).
    * **Action:** It creates a **`TestResult`** object linked to the `TestAssignment`.
    * **Action:** The system automatically compares `result_value` with the reference range to set the `flag` (N, H, L).

***

### Phase 3: Reporting (The Finalization)

1.  **Verification:** A supervisor reviews the results (`/results/verify/`).
    * **Action:** Sets `TestResult.verified_by` and `TestResult.verified_at`.
2.  **Order Completion:** Once all `TestAssignment`s for a `TestRequest` are verified, the `TestRequest` status is automatically updated to 'Verified'.
    * **Action:** The final report (PDF) is generated and the result is marked as **`TestResult.released = True`**.

This flow provides a comprehensive, traceable, and secure process for your multi-tenant LIMS.
