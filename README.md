# 🧪 FirstJP LIMS — Multi-Tenant Laboratory Information Management System

**FirstJP LIMS** is a modern, modular Laboratory Information Management System (LIMS) built with **Django**, designed to support **multi-tenant architecture** — where multiple laboratories (vendors) operate independently under one platform.

Each lab (tenant) has its own domain/subdomain, users, and data isolation.
The system supports various user roles such as **Platform Admin**, **Vendor Admin**, **Lab Staff**, **Clinician**, and **Patient**.

---

## 🚀 Key Features

* **Multi-Tenant Architecture**

  * Tenant resolution via subdomain (e.g., `carbon12.localhost.test:5050`)
  * Isolated data per vendor with shared core models

* **Role-Based Access**

  * Platform Admin: Global control and vendor management
  * Vendor Admin: Manages lab operations, staff, and test catalogs
  * Lab Staff: Handles sample collection, verification, and reporting
  * Clinician: Requests and reviews test results
  * Patient: Accesses personal test results securely

* **Authentication**

  * Tenant-aware login and registration
  * Role-restricted user registration (per vendor)
  * Secure password management and session handling

* **Core LIMS Workflow**

  1. Patient Registration
  2. Test Request Creation
  3. Sample Collection & Barcode Assignment
  4. Sample Reception & Verification
  5. Test Assignment and Processing
  6. Result Entry & Validation

* **Vendor Management**

  * Vendor onboarding (by Platform Admin)
  * Customizable test pricing and turnaround times (via `VendorTest` model)
  * Automatic barcode generation for samples

---

## 🏗️ Tech Stack

| Component       | Technology                                     |
| --------------- | ---------------------------------------------- |
| Backend         | Django 5.x                                     |
| Frontend        | Django Templating (Jinja2)                     |
| Database        | PostgreSQL (Recommended for schema separation) |
| Tenant Handling | Custom Middleware (`TenantMiddleware`)         |
| Authentication  | Django’s Custom User Model                     |
| Environment     | Python 3.12+, Virtual Environment              |

---

## ⚙️ Installation & Setup

```bash
# 1️⃣ Clone the repository
git clone repo

cd firstjp-lims

# 2️⃣ Create and activate a virtual environment
python -m venv .venv

.venv\Scripts\activate # On Mac: source .venv/bin/activate

# 3️⃣ Install dependencies
pip install -r requirements.txt

# 4️⃣ Apply migrations
python manage.py migrations
python manage.py migrate

# 5️⃣ Run the development server
python manage.py runserver

```
---
```
  Create Test Request  →  Collect Sample  →  Verify/Approve Sample  →  Perform Analysis  →  Record Results  →  Review/Verify Report
```
---

## 🌐 Tenant Configuration

### Example: Vendor Subdomain Setup

| Vendor             | Domain                    | URL                                                                        |
| ------------------ | ------------------------- | -------------------------------------------------------------------------- |
| Carbon12 Labs      | `carbon12.localhost.test` | [http://carbon12.localhost.test:5050](http://carbon12.localhost.test:5050) |
| MedPro Diagnostics | `medpro.localhost.test`   | [http://medpro.localhost.test:5050](http://medpro.localhost.test:5050)     |

Each domain is linked via the `VendorDomain` model in the admin panel or through the onboarding form.

---

## 👥 User Roles Overview

| Role               | Description                                  | Access Domain    |
| ------------------ | -------------------------------------------- | ---------------- |
| **Platform Admin** | Oversees platform-wide operations            | Main domain      |
| **Vendor Admin**   | Manages one lab/vendor account               | Vendor subdomain |
| **Lab Staff**      | Operates within lab (sample, result, report) | Vendor subdomain |
| **Clinician**      | Requests and views patient tests             | Vendor subdomain |
| **Patient**        | Views own test results                       | Vendor subdomain |

---

## 🧭 Development Notes

* Always test using vendor subdomains (`<vendor>.localhost.test:5050`)
* Use `TenantMiddleware` to attach `request.tenant` dynamically
* Vendor Admins are created only by Platform Admins
* Other roles register within their vendor’s subdomain only

---

## 📜 License

MIT License © 2025
