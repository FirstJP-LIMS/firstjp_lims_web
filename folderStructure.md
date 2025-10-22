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
