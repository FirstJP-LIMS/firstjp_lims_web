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



<!-- firstjp_lims_web/                  # repo root
├─ .github/                     # CI/CD
├─ deploy/                      # deployment scripts (systemd, nginx, gunicorn)
│  ├─ deploy_nginx.conf.j2
│  ├─ systemd/
│  └─ letsencrypt/
├─ docs/
├─ requirements.txt
├─ manage.py
├─ universal_lis/               # project settings
│  ├─ __init__.py
│  ├─ settings/
│  │  ├─ base.py
│  │  ├─ production.py
│  │  └─ local.py
│  ├─ urls.py
│  └─ wsgi.py / asgi.py
├─ apps/
│  ├─ core/                     # tenant-aware middleware, helpers
│  │  ├─ models.py              # Tenant model, Tenant config
│  │  ├─ middleware.py          # Tenant middleware
│  │  └─ templatetags/
│  ├─ accounts/                 # custom user model, auth, templates
│  │  ├─ models.py              # CustomUser
│  │  ├─ views.py               # login/logout/profile
│  │  └─ templates/accounts/
│  ├─ tenants/                  # tenant management UI (admin only)
│  ├─ vendors/                  # vendor (lab) domain logic, profiles
│  ├─ instruments/              # instrument models, instrument types
│  ├─ windows_connector/        # models + API + registration for Windows service
│  ├─ api/                      # DRF endpoints, token auth, versioned
│  └─ admin_dashboard/          # admin site views (analytics)
├─ templates/                    # global templates fallback
│  ├─ base.html
│  └─ accounts/
├─ static/
└─ tests/ -->
