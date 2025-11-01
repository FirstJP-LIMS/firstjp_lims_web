subdomain --- 
#  127.0.0.1   vendor1.localhost
#  127.0.0.1   carboni1.localhost
# 127.0.0.1   vendor2.localhost
#  127.0.0.1   labx.localhost


## 🚀 FirstJP LIMS Multi-Tenant Architecture

### Multi-Tenant Architecture Overview

This project is built on a **Shared Database, Shared Schema** multi-tenant architecture, allowing a single deployment to serve multiple independent laboratories/vendors under unique domain names (e.g., `labone.lis.com`, `labtwo.lis.com`).

The entire system is secured through mandatory tenant identification and data scoping at the database level.

### Key Architectural Decisions

1.  **Shared Infrastructure:** A single Django application instance and a single database server manage all vendor data.
2.  **Tenant Registry:** The **`Vendor`** and **`VendorDomain`** models (`apps/tenants/models.py`) act as the central registry, mapping incoming domain names to an internal `Vendor` entity.
3.  **Shared Identity:** A single, unified `accounts` system manages all users. Every user is linked to a single `Vendor` via a mandatory Foreign Key (`TenantId`).
4.  **Enforced Isolation:** Data isolation is guaranteed through application logic, not database separation.

### Core Component Breakdown

| Component | File/Location | Function | Multi-Tenancy Role |
| :--- | :--- | :--- | :--- |
| **Tenant Resolution** | `core/middleware.py` | Extracts the host/domain from the request or the `X-Tenant-ID` header. | **Crucial Entry Point:** Resolves the domain to a `Vendor` object and attaches it to the request as **`request.tenant`**. |
| **Tenant Registry** | `apps/tenants/models.py` | Defines the `Vendor` (the tenant entity) and `VendorDomain` (the domain-to-vendor mapping) models. | **Domain Mapping:** Links external domains to the internal `Vendor` object used for scoping. |
| **Data Scoping Manager** | `core/managers.py` | Defines the `TenantAwareManager`. | **Security Guarantee:** Enforces that every database query on a tenant-specific model (e.g., `SampleRequest`) *must* be filtered by `request.tenant`. Un-scoped queries are explicitly prevented. |
| **Tenant Data Models** | `apps/labs/models.py` (and others) | Defines models like `SampleRequest`. | **Data Structure:** Contains a mandatory `ForeignKey` to the `Vendor` model, establishing the **`TenantId` column** on all tenant-specific tables. |

### Deployment Considerations (Next Steps)

For this architecture to work, the deployment environment must support the following:

* **NGINX/Reverse Proxy:** Must be configured to forward traffic from all unique vendor domains (`*.lis.com`) to the single backend application host.
* **DNS Wildcard:** A wildcard DNS record (`*.lis.com` or similar) must be pointed to the server's IP address.
