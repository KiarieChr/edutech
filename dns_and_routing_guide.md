# Wildcard Subdomain Routing & DNS Guide 🌐

You have successfully implemented enterprise-grade wildcard subdomain routing for `django-tenants`. Here is how it all works and how to configure your DNS for production.

## 1. Architectural Changes Made

### Custom Middleware Fallback
Previously, if someone visited `nonexistent.royalsoftwares.co.ke`, your Django app would crash with a hard 404 error. 
- **Solution:** I created `apps/core/middleware.py`. Now, if a tenant doesn't exist, it gracefully falls back to the `public` schema, allowing you to show a landing page or "Sign Up" page on unmatched subdomains.

### URL Isolation
Your APIs were blended together. 
- **Solution:** I separated them!
- `config/urls_public.py`: Used ONLY by the public schema (Landing pages, Tenant Creation endpoint).
- `config/urls.py`: Used ONLY by your tenants (Dashboards, Academics, Finance APIs).

### New Features
- Added `description` and `settings` to the `Client` model, and `status` to `Domain`.
- Added `TenantInfoView` and `DashboardStatsView` APIs.
- Added CLI commands: `python manage.py create_tenant_subdomain` and `python manage.py list_tenants`.

---

## 2. DNS Configuration (Crucial Step)

To route `*.royalsoftwares.co.ke` to your server, you MUST configure a Wildcard A Record in your DNS provider (Cloudflare, AWS Route53, GoDaddy, etc.).

1. **Log in** to your DNS provider.
2. **Add a new record**:
   - **Type:** `A`
   - **Name/Host:** `*` (Just an asterisk)
   - **Value/Points To:** Your Server's Public IP Address (e.g., `123.45.67.89`)
   - **TTL:** Auto or 3600

> [!IMPORTANT]
> If you are using Cloudflare, you **cannot** proxy (Orange Cloud) a wildcard record unless you have an Enterprise plan. You must set it to **DNS Only** (Gray Cloud) for the wildcard to resolve properly.

---

## 3. Let's Encrypt SSL for Wildcards

You cannot use the standard `certbot --nginx` HTTP challenge for wildcard certificates (`*.royalsoftwares.co.ke`). Wildcards **require a DNS-01 Challenge**.

### How to generate a Wildcard SSL Certificate:
Run this on your server:
```bash
sudo certbot certonly --manual --preferred-challenges dns -d "*.royalsoftwares.co.ke" -d "royalsoftwares.co.ke"
```

1. Certbot will pause and give you a `TXT` record name (usually `_acme-challenge.royalsoftwares.co.ke`) and a random string value.
2. Go to your DNS provider and create this `TXT` record.
3. Wait 1-2 minutes for DNS propagation, then press Enter in your terminal.
4. Certbot will verify the DNS record and issue your wildcard certificate!

*Note: You will need to update your Nginx configuration manually to point to this new certificate path if Certbot doesn't do it automatically since we used `certonly`.*

---

## 4. Troubleshooting Routing Issues

**Symptom:** API requests to `prosper.royalsoftwares.co.ke/api/tenant/info/` return CORS errors.
**Fix:** Ensure your frontend URL strictly matches one of the regexes in `CORS_ALLOWED_ORIGIN_REGEXES` inside `config/settings/production.py`.

**Symptom:** 404 Error when creating a new tenant.
**Fix:** You must run migrations first! Since I updated the `Client` model, run `python manage.py makemigrations tenants` and `python manage.py migrate_schemas --shared`.
