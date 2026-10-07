# Deploy EIDREN on Render

This guide turns the included application into your store. The code is prepared for deployment; a live Render service, a funded payment account, real inventory, shipping operations, tax configuration, and your business's approved policies are still required.

## 1. Prepare your repository and business content

Push the contents of this folder to a Git repository you control. Keep `.env`, database files, passwords, OTP secrets, and payment keys out of Git. The supplied `render.yaml` assumes this folder is the repository root; if it is nested, configure Render's Root Directory accordingly.

The Blueprint requests paid web and database services to support an always-available storefront, pre-deploy migrations, and persistent data. Review the selected plans and current billing in Render before applying. No paid resources are created by the local code.

Review all customer-facing text and images. The demo catalog is fictional and is blocked from live payment. Publish accurate privacy, shipping, returns, and terms pages, contact details, business identity, product provenance, condition, warranty, and any legally required disclosures. Your business must choose the countries it serves and handle its applicable tax obligations. The software does not determine those obligations.

## 2. Create the Render services

1. In Render, choose **New → Blueprint** and connect your repository.
2. Review `eidren-watch-store` and `eidren-db`. They share the Oregon region by default. The database external-access list is empty, keeping access on Render's private network.
3. Enter the requested environment values below. The Blueprint generates `SECRET_KEY` and connects `DATABASE_URL` for you.
4. Apply the Blueprint. The build installs exact dependency versions, checks production configuration, and collects static files. The pre-deploy command applies database migrations, then Gunicorn serves the app.
5. Use Render's HTTPS hostname initially, or attach your custom domain and update the three origin settings together.

For manual creation, make a managed PostgreSQL database and Python web service in the same region. Set **Build Command** to `bash build.sh`, **Pre-deploy Command** to `python manage.py migrate --noinput`, **Start Command** to the value in `render.yaml`, and **Health Check Path** to `/health/`. Set `DATABASE_URL` to the database's internal connection string. Pre-deploy commands require an eligible paid service. Do not deploy production with SQLite.

## 3. Set environment variables

| Variable | Production value |
|---|---|
| `DEBUG` | `false` |
| `DEMO_MODE` | `false`; never enable for real sales |
| `SECRET_KEY` | Unique random secret with at least 256 bits of entropy; Blueprint generates it. For manual setup use `python -c "import secrets; print(secrets.token_urlsafe(64))"` |
| `DATABASE_URL` | Render PostgreSQL internal URL; Blueprint supplies it |
| `DATABASE_REQUIRE_SSL` | `true` |
| `SITE_URL` | Canonical HTTPS origin, e.g. `https://your-store.onrender.com`; no trailing path |
| `ALLOWED_HOSTS` | Exact comma-separated hostnames, e.g. `your-store.onrender.com,www.yourdomain.com`; no schemes |
| `CSRF_TRUSTED_ORIGINS` | Exact comma-separated HTTPS origins, e.g. `https://your-store.onrender.com,https://www.yourdomain.com` |
| `STORE_NAME` | Your public business/store name |
| `STORE_EMAIL` | A monitored customer-service email address |
| `STRIPE_SECRET_KEY` | Start with your Stripe test secret (`sk_test_…`); use `sk_live_…` only after launch checks |
| `STRIPE_WEBHOOK_SECRET` | Signing secret (`whsec_…`) for this exact endpoint and Stripe mode |
| `STRIPE_AUTOMATIC_TAX` | `true` only after configuring Stripe Tax and registrations; default `false` |
| `SHIPPING_COUNTRIES` | Comma-separated Stripe-supported two-letter countries, e.g. `US,CA` |
| `SHIPPING_RATE_CENTS` | Non-negative flat shipping price in USD cents, e.g. `1500` = $15; `0` = complimentary |
| `PYTHON_VERSION` | `3.12.14`, as pinned in the Blueprint |

The configured storefront currency is USD. Local product prices are the source of truth; Stripe price IDs are not needed. The shipping rate is a single flat rate for the order. Change both the software and store policy before offering multiple shipping methods or currencies.

Optional SMTP values are `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USE_TLS`, `EMAIL_HOST_USER`, and `EMAIL_HOST_PASSWORD`. These reserve a standard Django mail transport for operational use; the application does not provide marketing campaigns or shipment emails. Enable successful-payment receipts and customer support details in Stripe separately.

On Render, the provided `RENDER_EXTERNAL_HOSTNAME` is automatically trusted as a host and enables TLS proxy handling. On another platform, enable `TRUST_PROXY_SSL=true` only if your ingress replaces the inbound `X-Forwarded-Proto` header. The application ignores visitor-provided forwarding headers for client-IP lockouts unless `TRUSTED_PROXY_CIDRS` explicitly identifies trusted ingress networks. Leave this empty until you have verified the network path; username lockouts remain effective, but shared proxy IPs may cause shared lockouts. Never set it to all networks. Database-backed lockout works across app workers.

## 4. Set up secure administration

In the Render service's **Shell**, run:

```bash
python manage.py createsuperuser
python manage.py enroll_admin_otp YOUR_USERNAME
```

Use a unique password of at least 14 characters. The enrollment command shows a private time-based authenticator secret. Enter it in your authenticator app (SHA1, six digits, 30-second period), then enter the generated code to complete enrollment. Treat shell access and scrollback as sensitive; do not share the secret or put it in logs/screenshots. At `/admin/`, first submit username/password to reveal the device selector, then choose your device and enter a fresh code. The admin requires both factors.

For an emergency backup, from that trusted shell run `python manage.py addstatictoken YOUR_USERNAME` and store the one-use token in your password manager. This token can substitute for the authenticator code once. For a lost device, verify the account owner through your own process, then run `python manage.py enroll_admin_otp YOUR_USERNAME --replace`. The old authenticator remains valid until the new one is successfully verified. Revoke old backup tokens in the admin afterward. Do not turn off two-factor protection to regain access.

After five failed password attempts, sign-in is locked for an hour. A trusted administrator can reset a specific username with `python manage.py axes_reset_username YOUR_USERNAME`. If the connecting IP is also locked, use `python manage.py axes_reset_ip ACTUAL_IP`; only reset after investigating. Protect access to Render, your source repository, Stripe, and the database with their own two-factor authentication.

Create real product listings and approved Pages in admin. The deployment never automatically runs `seed_demo`. Sample listings are not inventory. Use an external HTTPS image host or versioned bundled assets; Render's ephemeral filesystem is not image storage.

## 5. Connect Stripe

1. In your Stripe test environment, copy your secret API key to Render as `STRIPE_SECRET_KEY`.
2. In Stripe **Workbench → Webhooks**, create a **snapshot** event destination for your own account at `https://YOUR_DOMAIN/webhooks/stripe/`.
3. Select `checkout.session.completed`, `checkout.session.expired`, `checkout.session.async_payment_succeeded`, and `charge.refunded`. Use a current stable API version and run the full test flow below after any version change.
4. Copy that destination's signing secret into `STRIPE_WEBHOOK_SECRET`, then redeploy/restart so the new value is loaded.
5. If using Stripe Tax, configure the appropriate registrations, business address, and default physical-product tax category in Stripe before enabling `STRIPE_AUTOMATIC_TAX`. Confirm tax results for each served region.

For local development, install the official Stripe CLI, run `stripe login`, then:

```bash
stripe listen --forward-to http://127.0.0.1:8000/webhooks/stripe/
```

Put the listener's signing secret in your local `.env`. CLI listener secrets and deployed destination secrets are different. Restart the local server when environment values change.

The backend verifies the raw-body signature, confirms payment details, and records processed event IDs. A customer's return to the thank-you page is not authorization to ship. Check the paid order in admin and Stripe. Orders with a mismatch are held for review. Do not manually mark such orders shipped until the discrepancy is resolved.

## 6. Verify before accepting real money

Use test keys first. Create a real test listing or, only on a separate staging service with `DEMO_MODE=true`, seed sample watches. Demo items never work with live keys.

- Complete a Checkout purchase with Stripe's test card `4242 4242 4242 4242`, any future expiry, and any three-digit CVC. Confirm the expected server price, shipping, tax, and total.
- Confirm the destination delivers successfully, the order becomes **Paid** exactly once, and the reserved stock is not decremented twice.
- Resend the same webhook from Stripe; verify the order and stock remain correct.
- Try a decline and an authentication-required test payment using Stripe's current [test-card guide](https://docs.stripe.com/testing). Never use real card data in test mode.
- Cancel or expire a Checkout session and confirm available stock returns once. Check overlapping attempts for the last available unit.
- Verify that altering browser form fields cannot change product prices and that missing or invalid webhook signatures are rejected.
- Refund a test payment in Stripe and confirm the admin's order status reflects the event. Restock returned goods separately after inspection.
- Check mobile layout, keyboard use, image loading, no broken links, cart editing, stock messages, payment failures, policy pages, admin two-factor login, and sign-in lockout.
- Confirm `/health/` is healthy, HTTPS is enforced, and `python manage.py check --deploy --fail-level WARNING` passes.
- Run the test suite against PostgreSQL, which is the production engine; SQLite cannot validate PostgreSQL row-lock concurrency semantics.
- Ensure database backups are enabled, conduct a restore rehearsal, configure monitoring, and verify you can recover admin access.

When all checks pass, use the live Stripe key and the separate live-mode webhook destination/secret. Keep `DEMO_MODE=false`, remove or deactivate all sample listings, publish final policies, and place a small authorized live order to confirm the real payment/refund path. Switching keys alone does not finish the business setup.

## 7. Operate and recover

Monitor Render error rates/health, Stripe webhook failures, pending orders, payment-review orders, stock discrepancies, and support email. Handle refunds/disputes in Stripe. Stripe sends payment receipts only when enabled in your account. Restrict staff permissions to the tasks each person needs.

Schedule `python manage.py reconcile_orders --limit 500` every five minutes and `python manage.py clearsessions` daily. Reconciliation uses the same database and Stripe mode as the web service. It recovers incomplete local records and releases stock only after confirmed session expiry, or confirmed absence after the creation window has passed. A Stripe timeout retains the reservation until the result is known. Do not release inventory manually after a timeout: a payment may already have succeeded.

Create a Render Cron Job using this repository, `python -m pip install -r requirements.txt` as its build command, `python manage.py reconcile_orders --limit 500` as its command, and `*/5 * * * *` as its schedule. Copy the web service's `DEBUG=false`, `DEMO_MODE=false`, `SECRET_KEY`, `DATABASE_URL`, `SITE_URL`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, and `STRIPE_SECRET_KEY` environment values. Alternatively place those values in a private shared Render environment group attached to both services. Use a second daily cron for `clearsessions`. Cron jobs are additional billed resources; review their plans before creating them. Run reconciliation once manually after first deployment to confirm access.

Back up PostgreSQL using the features of your chosen plan, retain backups according to your business's needs, and regularly restore into a separate test database. Protect backups because they contain customer contact/shipping information and authentication data. Configure a retention/deletion process suitable for your obligations. Keep payment records needed for refunds and disputes.

Before schema changes, take a backup and use backward-compatible migrations for rolling deploys. Render keeps the previous deploy serving if a build/pre-deploy step fails, but rolling back application code does not reverse database migrations. Restore only through an explicit recovery procedure after stopping conflicting writes.

Update pinned dependencies deliberately, run tests and production checks, deploy to staging, perform a test payment, then release. Do not assume a successful build establishes security forever. No third-party penetration test or payment-provider certification is included.

## References

- [Render deployment lifecycle and pre-deploy commands](https://render.com/docs/deploys)
- [Render Blueprint reference](https://render.com/docs/blueprint-spec)
- [Django deployment checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/)
- [Stripe webhooks and signature verification](https://docs.stripe.com/webhooks)
- [Stripe Checkout fulfillment](https://docs.stripe.com/checkout/fulfillment)
- [django-otp authenticator devices and emergency tokens](https://django-otp-official.readthedocs.io/en/stable/overview.html)
