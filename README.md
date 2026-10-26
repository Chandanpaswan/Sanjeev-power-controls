# Sanjeev Power Controls — Django website

A complete, database-backed demonstration website for **Sanjeev Power Controls**, a DG set
parts supplier. It includes a public marketing site, a searchable product catalogue and a
staff-only management dashboard.

> **Demonstration build.** Product names, SKUs, descriptions and specifications are sample
> content. No certification, capacity, compatibility, customer or approval claim is verified.
> Contact details are intentionally blank until the business supplies and approves them.
> Replace all sample content before a public launch.

Tagline: **Powering Performance. Ensuring Reliability.**

---

## What is included

### Public website

| Page | URL |
| --- | --- |
| Home | `/` |
| About us | `/about/` |
| Products catalogue | `/products/` |
| Product detail | `/products/<slug>/` |
| Quality & applications | `/quality/` |
| Blog list / article | `/blog/`, `/blog/<slug>/` |
| Contact / enquiry | `/contact/` |
| Enquiry confirmation | `/contact/thank-you/` |
| Privacy, terms, credits | `/privacy/`, `/terms/`, `/credits/` |
| Custom managed pages | `/<slug>/` (published pages only) |
| Sitemap / robots | `/sitemap.xml`, `/robots.txt` |

- Server-side search (name, SKU and description) and category filtering.
- Paginated catalogue, featured products on the home page and related products.
- Blog with categories, tags and search; published-only visibility.
- Draft managed pages return 404 and are excluded from navigation.
- Responsive layout, vendored Bootstrap 5, local fonts and no third-party tracking.
- Unique titles and meta descriptions, canonical URLs, Open Graph tags, JSON-LD structured
  data built only from stored fields, custom 404 and 500 pages, and a clear demo banner.
- Accessible enquiry form with CSRF protection, server-side validation, consent and a
  honeypot field. Submissions are saved to SQLite and receive a reference such as `SPC-4A19C2`.
- The site does **not** send email or WhatsApp messages. Staff follow up manually.

### Staff dashboard

| Area | URL |
| --- | --- |
| Sign in | `/admin-panel/login/` |
| Overview | `/admin-panel/` |
| Global search | `/admin-panel/search/` |
| Products | `/admin-panel/products/` |
| Categories | `/admin-panel/categories/` |
| Enquiries | `/admin-panel/enquiries/` |
| Customers | `/admin-panel/customers/` |
| Website pages | `/admin-panel/pages/` |
| Blog & blog categories | `/admin-panel/blog/` |
| Media library | `/admin-panel/media/` |
| Testimonials / FAQs / banners | `/admin-panel/testimonials/`, `/admin-panel/faqs/`, `/admin-panel/banners/` |
| Navigation menus | `/admin-panel/navigation/` |
| Website settings | `/admin-panel/settings/company/` (also contact, social, SEO, general) |
| Staff & roles | `/admin-panel/staff/`, `/admin-panel/roles/` |
| Notifications | `/admin-panel/notifications/` |
| Reports | `/admin-panel/reports/` |
| Activity log | `/admin-panel/activity/` |
| Backups | `/admin-panel/backup/` |
| My profile | `/admin-panel/profile/` |
| Django admin | `/django-admin/` |

- Dashboard statistics are calculated from the database, never hardcoded.
- Full product management: create/edit/duplicate/delete, image upload, gallery images,
  active/featured toggles, search and filters.
- Protected categories: a category with products cannot be deleted until its products are
  reassigned or removed. Categories without products can be deleted after confirmation.
- Enquiry workflow: text search, status/priority/date filters, pagination, CSV export, detail
  view, private notes, status changes, customer conversion and deletion with confirmation.
- Customer records with list/detail/edit/delete, CSV export and linked enquiries.
- Managed pages with sections, blog posts with categories/tags, media library, testimonials,
  FAQs, banners and drag-order navigation menus.
- Editable website settings for brand copy, hero text, footer text, contact fields, social
  profile URLs, SEO defaults, analytics ID, maintenance mode and indexing. Blank contact
  fields display clearly marked placeholders on the public site.
- Staff accounts and five role-based groups using Django model permissions; role management
  and CSV reports for enquiries, customers, activity and catalogue data.
- Superuser-only database backups (SQLite copy or JSON dump) with download and delete.
- Login lockout after repeated failures, CSRF protection, POST-only destructive actions and
  a `noindex` dashboard.
- Password reset flow for staff; with the default console email backend the reset link is
  printed to the server console instead of being sent.

---

## Technology

- Python 3.12+ (tested with Python 3.14)
- Django 5.2
- SQLite (PostgreSQL is configurable through environment variables)
- Django ORM and MVT templates
- Pillow for image validation/upload
- Bootstrap 5.3.3 (vendored locally), custom CSS and vanilla JavaScript
- `python-dotenv` for local environment configuration

---

## Project structure

```
config/                 Django project settings, URLs, WSGI/ASGI
core/                   Public core pages, SiteSettings, dashboard, staff auth, reports, backups
products/               Category/Product models, public catalogue, dashboard CRUD
enquiries/              Enquiry/Customer models, public submission, sales workflow
cms/                    Pages, blog, media, testimonials, FAQs, banners, navigation, redirects
templates/              Public and dashboard templates
static/                 CSS, JS, fonts, branding, photography and demo product renders
media/                  Runtime uploads (not committed)
backups/                Dashboard database backups (not committed)
manage.py
requirements.txt
.env.example
```

---

## Quick start (Windows PowerShell)

```powershell
cd C:\Code\Sanjeev-power-controls

# 1. Create and activate a virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Install dependencies
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

# 3. Create local environment configuration
Copy-Item .env.example .env
# Edit .env if you want to change the host, database or secret key.

# 4. Apply migrations
python manage.py migrate

# 5. Load demo categories, products, pages, menus and the standard roles
python manage.py seed_demo

# 6. Create your own dashboard superuser
python manage.py createsuperuser

# 7. Start the development server
python manage.py runserver
```

Open <http://127.0.0.1:8000/>. The dashboard is at
<http://127.0.0.1:8000/admin-panel/login/>.

If PowerShell blocks the activation script, run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

## Quick start (Linux / macOS)

```bash
cd Sanjeev-power-controls
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py seed_demo
python manage.py createsuperuser
python manage.py runserver
```

The development server is for local review only. Do not use `runserver` in production.

---

## Demo data

`python manage.py seed_demo` is idempotent. Running it again updates the demo records rather
than duplicating them.

It creates:

- Four categories: Filtration, Engine Spares, Electrical Components, Gaskets & Seals.
- Five sample products: DG Set Air Filter, Diesel Engine Oil Filter, Fuel Filter Assembly,
  Generator Alternator Component, DG Set Engine Spare Parts Kit.
- Demo renders copied into `media/products/` from `static/images/products/demo/`.
- Four published managed pages (Home, About Us, Quality & Applications, Contact Us) and
  13 header/footer menu items.
- Five standard roles with model permissions: Super Admin, Content Manager, Product Manager,
  Sales Manager, Viewer / Analyst.
- Default website settings when fields are blank.

Use `python manage.py seed_demo --reset-settings` to restore the demo brand/hero/footer copy.
It does not delete enquiries or overwrite uploaded product images.

The `Gaskets & Seals` category is intentionally empty so the safe-deletion behaviour can be
demonstrated in the dashboard.

`python manage.py setup_roles` refreshes the five roles independently. Run it after adding a
model that staff roles should be able to manage. Existing group assignments are preserved.

### Create additional staff accounts

1. Sign in as a superuser.
2. Open **Staff & roles → Add staff account**.
3. Tick one of the five roles:
   - **Super Admin** — complete dashboard access, including staff, roles, backups and reports.
   - **Content Manager** — pages, blog, media, testimonials, FAQs, banners, menus and settings.
   - **Product Manager** — products, categories, gallery images and catalogue media.
   - **Sales Manager** — enquiries, customers, follow-up, conversion and sales reports.
   - **Viewer / Analyst** — read-only access to content, catalogue, enquiries and reports.
4. New staff accounts are marked `is_staff` automatically. Only superusers can manage staff.

Alternative: `python manage.py createsuperuser` for another full-access account.

---

## Environment variables

Copy `.env.example` to `.env`. Never commit `.env`.

| Variable | Purpose |
| --- | --- |
| `DJANGO_SECRET_KEY` | Required when `DEBUG=False`. Generate a random value. |
| `DJANGO_DEBUG` | `True` locally, `False` in production. |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated host names. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Comma-separated HTTPS origins for form posts. |
| `DB_ENGINE` | Empty for SQLite. Set to `django.db.backends.postgresql` for PostgreSQL. |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | Database connection. |
| `SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS` | Production HTTPS controls. |
| `USE_X_FORWARDED_PROTO` | `True` behind a TLS-terminating reverse proxy. |
| `BACKUP_DIR` | Directory for dashboard backups. Defaults to `backups/`. Keep outside the web root. |
| `LOGIN_MAX_ATTEMPTS`, `LOGIN_LOCKOUT_SECONDS` | Sign-in lockout threshold and duration. |
| `SESSION_COOKIE_AGE` | Staff session lifetime in seconds. |
| `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | Optional future email delivery. No enquiry emails are sent by this build. |

Generate a production secret key:

```bash
python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"
```

---

## Content and claims

The site deliberately avoids inventing verifiable business facts. Before launch, confirm and
replace:

- [ ] Company history, founding year and ownership.
- [ ] Manufacturing capabilities, capacity, machinery and certifications.
- [ ] Product part numbers, dimensions, materials and compatibility.
- [ ] Customer names, testimonials, approvals and partnerships.
- [ ] Phone, email, WhatsApp, address, business hours and map embed.
- [ ] Social profile URLs.
- [ ] Privacy policy and terms wording reviewed by the business.
- [ ] Product images (replace demo renders with approved photography).
- [ ] SEO titles, descriptions and keywords.

Contact fields in the dashboard are blank by default. Every public page shows a marked
placeholder such as “Contact details to be confirmed” until a verified value is entered.

---

## Security notes

- The dashboard is restricted to active `is_staff` accounts and checks Django model
  permissions server-side.
- Five roles map to Django groups; role changes are applied through server-side forms.
- Passwords are hashed by Django. No plaintext password is stored in the repository or page.
- CSRF protection is enabled. Deletes and status toggles are POST-only and require confirmation.
- Uploads are restricted to JPG, PNG, WebP or GIF, with a 3 MB form limit and additional
  content-type/extension checks.
- CSV exports neutralise spreadsheet formula injection.
- Login failures are rate-limited in the local cache. For a multi-process deployment, configure
  a shared cache (Redis or Memcached) so the lockout applies across workers.
- Production settings enable secure cookies, HSTS, SSL redirect and `X-Frame-Options: DENY`
  when `DJANGO_DEBUG=False`.
- Database backups and CSV exports contain customer data. Backup download/delete is restricted
  to superusers; keep the `backups/` directory out of the web root and out of version control.
- The SQLite database, `.env` file, uploaded media, backups and Django admin logs are excluded
  by `.gitignore`.

Never commit `db.sqlite3`, `.env`, `media/` uploads, `backups/` archives, or customer enquiry
data.

---

## Deployment checklist

1. Set `DJANGO_DEBUG=False`, a strong `DJANGO_SECRET_KEY` and the real `DJANGO_ALLOWED_HOSTS`.
2. Configure PostgreSQL for a multi-user production deployment, or plan SQLite backups carefully.
3. Run:
   ```bash
   python manage.py migrate
   python manage.py collectstatic --noinput
   python manage.py check --deploy
   ```
4. Serve the WSGI app with a production server (for example Gunicorn behind Nginx). Do not use
   `runserver`.
5. Serve `/static/` from the web server or CDN. Serve `/media/` only after configuring upload
   storage and access controls.
6. Put TLS in front of the site and set `USE_X_FORWARDED_PROTO=True` if the proxy terminates TLS.
7. Configure real email delivery if staff should receive password-reset links by email;
   otherwise the console backend prints them to the server log.
8. Set `BACKUP_DIR` to a private location outside the web root and schedule off-server copies.
9. Create a real superuser and remove any demo accounts before launch.
10. Back up the database and uploaded media on a schedule. Test restoring the backup.
11. Replace all demo content and verify every product claim.

Suggested production commands:

```bash
python manage.py check --deploy
python manage.py collectstatic --noinput
gunicorn config.wsgi:application --bind 0.0.0.0:8000
```

---

## Verification commands

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate
python manage.py seed_demo
python manage.py setup_roles
```

Manual review checklist:

- Public pages, search, category filters, product detail, blog and managed pages.
- Enquiry submission, validation errors, honeypot and reference number.
- Dashboard sign-in, password-reset flow and profile page.
- Product/category CRUD, gallery uploads, safe category deletion and settings tabs.
- Enquiry status/notes, customer conversion, CSV export and deletion confirmation.
- Pages, blog, media, testimonials, FAQs, banners and navigation management.
- Staff accounts and role permissions (for example, a Viewer cannot edit records).
- Reports, activity log and a superuser-only backup create/download/delete cycle.
- 404 page, dynamic sitemap, robots file and maintenance mode.
- Mobile layout and keyboard navigation.

---

## Credits

Branding, demo product renders, photography placeholders and interface code were generated for
this demonstration build. See `/credits/` for the public asset notice. All content and claims
must be reviewed and approved by Sanjeev Power Controls before publication.
