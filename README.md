# 🧪 FirstJP LIMS — Multi-Tenant Laboratory Information Management System

**FirstJP LIMS** is a modular **Laboratory Information Management System (LIMS)** built with **Django**, designed for **multi-tenant laboratory operations**, where multiple independent laboratories operate securely under a shared platform.

Each tenant (lab/vendor) is isolated via **subdomain-based architecture**, ensuring strict data separation, role-based access control, and independent workflows.

The system exposes RESTful endpoints that can be consumed by external frontend applications.

---

## 🚀 Key Features

### 🏢 Multi-Tenant Architecture

* Subdomain-based tenant resolution (e.g., `carbon12.localhost.test:5050`)
* Strict data isolation per vendor
* Shared core infrastructure with tenant-scoped data access

---
### Architecture Diagram
![lims-architecture-diagram](https://github.com/Sevenwings26/lims-multitenant-system/main/lims-architecture-diagram.png?raw=true)
---

### 🔐 Role-Based Access Control (RBAC)

* **Platform Admin** → Global system and vendor management
* **Vendor Admin** → Manages lab operations, staff, and test catalog
* **Lab Staff** → Handles sample processing and result entry
* **Clinician** → Requests and reviews test results
* **Patient** → Secure access to personal test results

---

### 🔑 Authentication System

* Tenant-aware authentication flow
* Role-restricted registration per vendor
* Secure session handling with custom user model

---

### 🔬 Core LIMS Workflow

1. Patient registration
2. Test request creation
3. Sample collection & barcode assignment
4. Sample reception & verification
5. Test assignment and processing
6. Result entry, validation, and reporting

---

### 🧩 Vendor Management

* Vendor onboarding (Platform Admin controlled)
* Custom test catalog per vendor (`VendorTest` model)
* Barcode generation for sample tracking
* Independent operational configuration per lab

---

### 🌐 REST API Integration

The system exposes RESTful endpoints that can be integrated with external frontend systems, enabling decoupled UI development.

---

## 🏗️ Tech Stack

| Layer          | Technology                             |
| -------------- | -------------------------------------- |
| Backend        | Django 5.x                             |
| Frontend       | Django Templates (Jinja2)              |
| Database       | PostgreSQL                             |
| Multi-Tenancy  | Custom Middleware (`TenantMiddleware`) |
| Authentication | Custom Django User Model               |
| Environment    | Python 3.12+ (Virtual Environment)     |

---

## ⚙️ Installation & Setup

```bash
# 1. Clone repository
git clone https://github.com/Sevenwings26/lims-multitenant-system.git
cd lims-multitenant-system

# 2. Create virtual environment
uv venv

# Activate (Windows)
.venv\Scripts\activate

# Activate (Windows)
.venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Apply migrations
python manage.py makemigrations
python manage.py migrate

# 5. Run server
python manage.py runserver
```

---

## 🔄 System Workflow

```text
Patient Registration → Test Request → Sample Collection → Verification → Analysis → Result Entry → Review & Reporting
```

---

## 🌐 Tenant Configuration

### Example Vendor Subdomains

| Vendor             | Domain                  | URL                                                                        |
| ------------------ | ----------------------- | -------------------------------------------------------------------------- |
| Carbon12 Labs      | carbon12.localhost.test | [http://carbon12.localhost.test:5050](http://carbon12.localhost.test:5050) |
| MedPro Diagnostics | medpro.localhost.test   | [http://medpro.localhost.test:5050](http://medpro.localhost.test:5050)     |

Each tenant is mapped via the `VendorDomain` model and resolved dynamically using middleware.

---

## 👥 User Roles

| Role           | Description                                 |
| -------------- | ------------------------------------------- |
| Platform Admin | Oversees entire system and vendor lifecycle |
| Vendor Admin   | Manages lab operations and configurations   |
| Lab Staff      | Handles samples, testing, and reporting     |
| Clinician      | Requests tests and reviews results          |
| Patient        | Views personal test results securely        |

---

## 🧭 Development Notes

* Always test using tenant subdomains (`<vendor>.localhost.test`)
* Tenant context is resolved via `TenantMiddleware`
* Vendor Admin accounts are created only by Platform Admins
* Role-based access is enforced across all workflows
* External frontend systems can consume REST APIs independently

---

## 📌 Project Status

* Core system fully implemented
* REST API endpoints exposed for frontend integration
* Multi-tenant architecture functional and tested
* Some production deployments are currently offline due to infrastructure changes

---

## 📜 License

MIT License © 2026
