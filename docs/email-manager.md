# Email Manager

The Email Manager is the dashboard module that configures outgoing email for the
public enquiry form, staff notifications and the staff password-reset flow. It
lives at **Admin panel → Email Manager** (`/admin/email-manager/`).

Everything is stored in the database and visible in the dashboard:

| Section | URL | What it does |
| --- | --- | --- |
| Email Overview | `/admin/email-manager/` | Delivery statistics calculated from email logs |
| SMTP Settings | `/admin/email-manager/smtp/` | Server, credentials, sender identity, retries, retention |
| Test Email | `/admin/email-manager/test-email/` | Real SMTP connection test and real test message |
| Email Templates | `/admin/email-manager/templates/` | Subject, HTML body and plain-text body |
| Email Logs | `/admin/email-manager/logs/` | Searchable history of every attempt |
| Notification Rules | `/admin/email-manager/rules/` | Which event sends which template to whom |

---

## 1. Access and permissions

Every route checks Django permissions on the server. Hiding a menu link is not
the security boundary.

| Permission | Grants |
| --- | --- |
| `email_manager.manage_smtp` | SMTP settings and test email |
| `email_manager.view_emaillog` | Overview and email logs (read-only) |
| `email_manager.view_emailtemplate` | Template list, preview and read-only detail |
| `email_manager.change_emailtemplate` | Create, edit, activate and deactivate templates |
| `email_manager.delete_emailtemplate` | Delete non-system templates |
| `email_manager.view_notificationrule` | View notification rules |
| `email_manager.change_notificationrule` | Enable, disable and edit rules |

Superusers always have access. The `setup_roles` command grants:

- **Super Admin** — everything in the app.
- **Content Manager** — view logs, templates and rules.
- **Sales Manager** — view logs, templates and rules.
- **Viewer / Analyst** — read-only access to the whole app.

SMTP credentials are restricted to `manage_smtp` holders and superusers. Grant
that permission deliberately; it is equivalent to control of the company's
outgoing mail account.

Anonymous visitors are redirected to the dashboard login. Signed-in staff
without the required permission receive HTTP 403. Every POST is CSRF-protected.

---

## 2. First-time setup

```bash
python manage.py migrate
python manage.py setup_roles
python manage.py seed_email_manager
```

`migrate` also runs the same seeding through a `post_migrate` signal, so the
command is only needed if the defaults are missing. Seeding is idempotent and
never overwrites an edited template or rule.

The defaults that are created:

| Key | Used for |
| --- | --- |
| `new_enquiry_notification` | Internal copy of a general website enquiry |
| `customer_enquiry_acknowledgement` | Reply to the customer after an enquiry |
| `product_enquiry_notification` | Internal copy of a product enquiry |
| `admin_new_lead_alert` | Admin alert for a new lead |
| `contact_form_confirmation` | Public contact-form confirmation |
| `password_reset_email` | Staff password reset |
| `lead_assigned_alert` | Assignee alert |
| `enquiry_status_changed` | Internal status-change alert |
| `follow_up_reminder` | Daily follow-up reminder |

Outgoing email is **disabled by default**. Nothing is sent from the public site
until an administrator saves a working SMTP configuration and enables it.

---

## 3. SMTP settings

Open **Email Manager → SMTP Settings**.

| Field | Notes |
| --- | --- |
| Provider preset | Pre-fills host and port for Gmail or Microsoft 365 |
| SMTP host / port | Required when outgoing email is enabled |
| Username | Usually the full email address |
| Password / app password | Encrypted before it is stored |
| Sender email | The `From:` address |
| Sender display name | Shown next to the address |
| Reply-to | Optional; defaults to the sender address |
| Use STARTTLS | Port 587 style upgrade |
| Use SSL/TLS | Port 465 style implicit TLS |
| Timeout | Seconds to wait for the server (default 20) |
| Admin notification email | Receives internal alerts |
| Enable outgoing email | Master switch for all sends |
| Log retention | Days before old logs can be pruned (default 180) |

STARTTLS and implicit SSL are mutually exclusive; the form rejects both at once.

### Presets

| Preset | Host | Port | Encryption |
| --- | --- | --- | --- |
| Gmail | `smtp.gmail.com` | 587 | STARTTLS |
| Microsoft 365 | `smtp.office365.com` | 587 | STARTTLS |
| Custom | any | any | STARTTLS or SSL |

### Gmail

1. Enable 2-Step Verification on the Google account.
2. Create an **App password** (Google Account → Security → App passwords).
3. Use `smtp.gmail.com`, port `587`, STARTTLS, and the app password — **not**
   the normal account password.
4. Google Workspace administrators may need to allow SMTP AUTH for the tenant.

Google can disable app passwords for accounts without 2-Step Verification, and
"less secure app access" no longer exists. If authentication fails, create a new
app password.

### Microsoft 365

1. The mailbox must be licensed for Exchange Online.
2. An administrator must enable **SMTP AUTH** for the mailbox or organisation
   (`Set-CASMailbox -Identity user@domain -SmtpClientAuthenticationDisabled $false`
   or the equivalent Microsoft 365 admin centre setting). SMTP AUTH is disabled
   by default on new tenants.
3. Use `smtp.office365.com`, port `587`, STARTTLS.
4. Accounts with security defaults or conditional access may require an app
   password or OAuth; basic SMTP AUTH with a password can be blocked outright.

Microsoft periodically retires basic authentication methods. If SMTP AUTH is
refused, use a transactional provider (Amazon SES, SendGrid, Mailgun, Postmark)
and enter its SMTP host and credentials under **Custom**.

### Custom providers

Any standard SMTP relay works. Check the provider documentation for the correct
host, port and TLS mode. Common combinations:

- Port 587 with STARTTLS (most providers)
- Port 465 with implicit SSL
- Port 25 is usually blocked by hosting providers and should be avoided

### Password handling

- The password is encrypted with Fernet (AES-128-CBC + HMAC-SHA256) from the
  `cryptography` package.
- Only the ciphertext is stored. It is never rendered in HTML, JSON, logs or
  the Django admin.
- The edit form shows `••••••••` once a password is saved. Leaving the field
  blank keeps the existing password. Ticking **Clear saved password** removes
  it and is refused while outgoing email is still enabled.
- Passwords and message bodies are never written to `EmailLog`.

### Encryption key

Set `EMAIL_ENCRYPTION_KEY` in the server environment. It must not live in the
database or the repository.

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

A long random passphrase is also accepted; it is hashed with SHA-256 first.
In `DEBUG=True` mode only, a development key is derived from
`DJANGO_SECRET_KEY` so local development works without extra setup. Production
(`DEBUG=False`) refuses to encrypt secrets without a dedicated key, and
`python manage.py check` reports `email_manager.W002`.

Losing the key makes saved SMTP passwords unreadable. Changing the key requires
re-entering the password. Back the key up with the rest of your server secrets.

---

## 4. Test email

**Email Manager → Test Email** offers two actions:

1. **Test connection** — opens an SMTP connection, authenticates and issues
   `NOOP`. No message is sent.
2. **Send test email** — sends a real message through the configured server.

Both use the saved configuration, not unsaved form values. Results are shown as
sanitised messages, for example:

- "The mail server accepted the username and password."
- "The mail server rejected the username or password. Check the username and
  app password and confirm that SMTP AUTH is enabled."
- "The connection timed out. Check the host, port and firewall."
- "The server requires a secure connection. Check STARTTLS/SSL settings."

Test messages are recorded in Email Logs with the event **Test email**, so
repeated testing is visible without storing the message content.

---

## 5. Templates

Each template has a subject, an HTML body and a plain-text body.

- **Create / edit** — restricted to `change_emailtemplate`.
- **Preview** — renders with sample data in a sandboxed frame.
- **Activate / deactivate** — deactivated templates are logged as `skipped` and
  are not sent.
- **Delete** — only non-system templates; the six required templates cannot be
  deleted. A template that a notification rule still references is protected:
  point the rule at another template first.

### Placeholders

Only approved placeholders are allowed:

`customer_name`, `customer_email`, `customer_phone`, `company_name`,
`product_name`, `enquiry_id`, `enquiry_message`, `enquiry_status`,
`enquiry_url`, `old_status`, `new_status`, `assigned_to`, `site_name`,
`contact_email`, `admin_email`, `current_year`, `reset_url`, `protocol`,
`domain`.

Filters are limited to `default`, `upper`, `lower`, `title`, `capfirst`,
`date`, `time`, `truncatechars`, `truncatewords`, `linebreaks`, `linebreaksbr`,
`escape`, `urlize`, `yesno`, `length`, `pluralize`.
`|safe` and any filter that disables escaping are rejected.

The validator rejects:

- Any `{% ... %}` template tag (including `include`, `load`, `extends`).
- Unknown placeholders.
- Unclosed `{{ ... }}` braces.
- Unknown filters.

Rendering is done with Django's autoescaping enabled, then cleaned by a
conservative HTML sanitiser that removes scripts, frames, forms, event-handler
attributes and `javascript:` URLs. Customer input can never become executable
HTML in an email.

### Sample data

The preview uses fictional sample values (`sample_context()` in
`email_manager/defaults.py`). It never reads real customer records.

---

## 6. Notification rules

A rule connects an event to a template, a recipient and an optional condition.

| Event | Default template | Recipient |
| --- | --- | --- |
| New general enquiry (internal) | `new_enquiry_notification` | Admin notification email |
| New enquiry (customer) | `customer_enquiry_acknowledgement` | Enquirer |
| Product enquiry (internal) | `product_enquiry_notification` | Admin notification email |
| New lead alert | `admin_new_lead_alert` | Admin notification email |
| Contact form confirmation | `contact_form_confirmation` | Enquirer |
| Password reset | `password_reset_email` | Requesting staff member |
| Lead assigned | `lead_assigned_alert` | Assignee |
| Status changed | `enquiry_status_changed` | Admin notification email |
| Follow-up due | `follow_up_reminder` | Admin notification email |

Rules can be enabled or disabled independently. Customer data is only ever sent
to the enquirer's own address, the configured admin notification address, or the
staff member assigned to the enquiry. A rule cannot be pointed at an arbitrary
recipient through the public form.

Outgoing email is disabled by default, so no rule sends anything until an
administrator enables the service. When it is enabled, the core
acknowledgement, internal-notification and password-reset rules are active;
the optional lead alert, contact confirmation, assignment, status-change and
follow-up reminder rules start disabled.

---

## 7. Enquiry integration

The public enquiry flow (`/enquiries/submit/`) saves the enquiry **first**:

1. Validate the form.
2. Save the enquiry and generate its reference.
3. Send the customer acknowledgement.
4. Send the internal/admin notification.

Steps 3 and 4 are wrapped so that any email failure — SMTP outage, timeout,
misconfiguration or template error — is caught and logged. The enquiry is never
lost or rolled back because of email. A broken mail server cannot take the
website down.

Product enquiries include the product name, reference and a link when a product
is attached to the enquiry.

Each attempt creates an `EmailLog` row linked to the enquiry. The enquiry detail
page shows that history to staff with `view_emaillog`, and the sidebar link
opens the log list filtered by the enquiry reference.

**Delivery status semantics:**

| Status | Meaning |
| --- | --- |
| `queued` | Created but not yet attempted |
| `sent` | Accepted by the SMTP server — not proof of inbox delivery |
| `failed` | The attempt failed; a sanitised reason is recorded |
| `skipped` | Outgoing email is disabled, the rule/template is inactive, or the recipient is missing |
| `delivery_confirmed` | A provider webhook confirmed delivery (reserved; no webhook is included) |

The dashboard never claims that an email was "delivered" when it was only
accepted by SMTP.

### Duplicate protection

Every notification has a deterministic dedupe key built from the event, related
record and recipient. A second attempt for the same event returns the existing
log instead of sending again. This protects against double form submissions,
retried views and repeated management-command runs.

### Retries

Transient connection failures are retried automatically according to
`EMAIL_MANAGER_AUTO_RETRIES` and `EMAIL_MANAGER_RETRY_DELAY`. Every attempt
increments `attempts` on the same log record.

Manual retry is available from an email log when the message can be rebuilt from
its template and linked enquiry. Full bodies are deliberately not stored, so
free-form or test messages that cannot be reconstructed are not retryable. The
log detail page explains why a message is or is not retryable.

### Password reset

The staff password-reset form routes through the Email Manager when the
`password_reset` template and rule exist and are active. The reset email then uses
the configured SMTP account and appears in Email Logs. If the template or rule is
missing or disabled, Django's standard reset email is used instead, so password
reset never depends on the Email Manager being fully configured.

The reset link itself is a Django `PasswordResetTokenGenerator` token and follows
Django's normal expiry and single-use rules.

---

## 8. Logs

Each row stores:

- Recipient address and display name
- Sender address
- Subject
- Template key and template name
- Related enquiry (when applicable)
- Event
- Status and attempt count
- Created / updated timestamp
- Sanitised error summary
- SMTP message ID (when accepted)
- Dedupe key

Logs **never** store the SMTP password, the full message body, reset tokens or
attachments.

The list supports free-text search (recipient, subject, enquiry reference),
status/event/date filters and pagination. Errors are mapped to short,
operator-friendly summaries:

| Failure | Summary |
| --- | --- |
| `SMTPAuthenticationError` | Username or app password rejected |
| `SMTPRecipientsRefused` | Recipient rejected |
| `SMTPServerDisconnected` | Server closed the connection |
| `SMTPConnectError` | Could not connect to host/port |
| `TimeoutError` / `socket.timeout` | Connection timed out |
| `ssl.SSLError` | Secure connection failed |
| `ConnectionRefusedError` | Connection refused |
| Unknown | "An unexpected error occurred" — details in the server log only |

Raw exception text is never shown in the dashboard.

### Retention

`EMAIL_LOG_RETENTION_DAYS` (and the per-install log retention field) controls
how long records are kept. Prune manually or schedule the command:

```bash
python manage.py prune_email_logs --dry-run
python manage.py prune_email_logs
python manage.py prune_email_logs --days 90
```

---

## 9. Management commands

| Command | Purpose |
| --- | --- |
| `python manage.py seed_email_manager` | Create missing default templates and rules |
| `python manage.py retry_failed_emails --limit 25` | Retry rebuildable failures (add `--dry-run` to list) |
| `python manage.py send_follow_up_reminders` | Email reminders for due follow-ups (add `--dry-run`) |
| `python manage.py prune_email_logs` | Delete logs older than the retention period |

`send_follow_up_reminders` is idempotent for a given follow-up date because the
dedupe key includes it. Schedule it once a day, for example:

```cron
0 8 * * * cd /srv/app && .venv/bin/python manage.py send_follow_up_reminders
30 2 * * 0 cd /srv/app && .venv/bin/python manage.py prune_email_logs
```

On Windows, use Task Scheduler with the equivalent command. On Vercel or other
serverless hosts, use the platform scheduler (Vercel Cron) to call a protected
management endpoint or an external scheduler against a small admin-only view.

---

## 10. Sending architecture

All outgoing mail goes through `email_manager.mailer`:

```
enquiries.views / notifications / core.forms
                │
                ▼
      email_manager.notifications   (events, rules, recipients, dedupe)
                │
                ▼
        email_manager.mailer        (validation, retries, logs, sanitising)
                │
                ▼
   Django EmailMultiAlternatives / SMTP backend
```

Two transports are available:

| `EMAIL_MANAGER_TRANSPORT` | Behaviour |
| --- | --- |
| `database` (default) | Uses the encrypted SMTP settings saved in the dashboard |
| `django` | Uses `settings.EMAIL_BACKEND`; used by tests with the in-memory backend |

Sending is synchronous. That is appropriate for a small site: the SMTP timeout
bounds the request, errors are caught, and the enquiry is already saved. For
high volume, move sending to a queue:

1. Keep the `EmailLog` row in `queued` status when it is created.
2. Push `(log_id)` onto a worker queue (Celery, RQ, Dramatiq, a database outbox
   or a platform queue).
3. Let the worker call `mailer.send_template_email(...)` / `notifications.retry_email_log(...)`
   and update the same row.
4. Add a periodic job that retries `queued` and `failed` records.

The service layer, dedupe keys and statuses are already queue-friendly; only the
enqueue step needs to be added.

Deployments behind a request timeout (serverless functions) should shorten
`EMAIL_TIMEOUT` and prefer asynchronous sending, because the platform may cut
off a slow SMTP handshake.

---

## 11. Production checklist

- [ ] `EMAIL_ENCRYPTION_KEY` set from the server environment.
- [ ] `DJANGO_DEBUG=False` and a strong `DJANGO_SECRET_KEY`.
- [ ] HTTPS enforced (`SECURE_SSL_REDIRECT=True`, HSTS configured).
- [ ] `DJANGO_ALLOWED_HOSTS` and `DJANGO_CSRF_TRUSTED_ORIGINS` list the real domain.
- [ ] `SITE_BASE_URL` set to the public HTTPS origin.
- [ ] SMTP configured, **Test connection** and **Send test email** both succeed.
- [ ] Sender address is authorised by the mail provider (SPF/DKIM alignment).
- [ ] Outgoing email enabled deliberately, with the rules you want.
- [ ] Admin notification address is a monitored mailbox.
- [ ] Log retention scheduled.
- [ ] `python manage.py check --deploy` passes.
- [ ] `.env`, `db.sqlite3`, backups and media remain untracked by git.

Sender reputation: use a domain you control, publish SPF and DKIM records, and
consider a dedicated transactional provider. Gmail and Microsoft 365 both impose
sending limits and may treat bulk mail from a personal mailbox as spam.

---

## 12. Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `email_manager.W001` / `W002` check warning | `EMAIL_ENCRYPTION_KEY` missing | Set the key; restart the app |
| Password field will not accept a blank save | A username is set without a saved password | Enter the password, or clear the username |
| **Test connection** times out | Firewall, wrong port, blocked outbound SMTP | Try 587/465, ask the host to allow SMTP |
| "rejected the username or password" | Normal password used instead of app password, or SMTP AUTH disabled | Create an app password / enable SMTP AUTH |
| "server requires a secure connection" | STARTTLS/SSL mismatch | Port 587 + STARTTLS, or port 465 + SSL |
| Emails logged as `skipped` | Outgoing email disabled, rule/template inactive, or no recipient | Check SMTP Settings and Notification Rules |
| Emails logged as `sent` but not received | Accepted by SMTP, then filtered or dropped | Check spam, provider logs, SPF/DKIM |
| No customer acknowledgement | Rule disabled or admin address missing | Enable the rule and set the admin notification email |
| No password reset email | Rule disabled or SMTP not configured | Enable the rule; otherwise Django's fallback email is used |
| Dashboard shows 403 | Missing permission | Grant the relevant `email_manager.*` permission or a role |
| Logs not appearing | Table not migrated | Run `python manage.py migrate` |

Server-side logs contain the raw exception for diagnosis. Do not copy SMTP
passwords or full customer messages into tickets.

---

## 13. Tests

```bash
python manage.py test email_manager
```

The suite covers:

- Secret encryption, masking and the production key requirement.
- Template placeholder validation, tag rejection, escaping and sanitisation.
- SMTP form validation, TLS/SSL conflict, password preservation and clearing.
- Successful test email with Django's in-memory backend.
- Failure handling with sanitised errors.
- Enquiry persistence when email sending raises.
- Dedupe, retry and attempt counting.
- Default template/rule seeding.
- Dashboard authorisation, CSRF enforcement and password masking in HTML.
- Password reset routing and fallback.

Tests use `EMAIL_MANAGER_TRANSPORT=django` with
`django.core.mail.backends.locmem.EmailBackend`, so they never contact a real
mail server.
