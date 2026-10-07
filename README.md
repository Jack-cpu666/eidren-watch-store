# EIDREN — an immersive watch boutique

A responsive watch storefront with a Python/Django backend, a protected inventory and order administration panel, and Stripe-hosted Checkout. Designed for deployment on Render with managed PostgreSQL.

The included watches and photography are presentation samples. No real payment credentials, customer accounts, or live deployment are included. Replace the samples with accurate inventory before opening the store.

## What is included

- Responsive storefront, collection browsing, product details, shopping bag, and order confirmation.
- Admin controls for products, prices, stock, featured listings, store policies, fulfillment, and tracking.
- Mandatory authenticator verification for every admin account, Argon2 passwords, persistent sign-in lockout, CSRF protection, secure cookies, HTTPS enforcement, and a content security policy.
- Server-calculated USD prices, stock reservations, Stripe-hosted card payment, signed webhooks, duplicate-event handling, and payment reconciliation.
- Render configuration, database migrations, pinned dependencies, and tests for important commerce and security boundaries.

## Run locally

Use Python 3.12. On Windows, open PowerShell in this folder:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py seed_demo
.\.venv\Scripts\python.exe manage.py createsuperuser
.\.venv\Scripts\python.exe manage.py enroll_admin_otp YOUR_USERNAME
.\.venv\Scripts\python.exe manage.py runserver
```

On macOS/Linux use `python3 -m venv .venv`, `source .venv/bin/activate`, `cp .env.example .env`, and `python` for subsequent commands. The commands below assume the environment is activated.

Open **http://127.0.0.1:8000/** for the store and **http://127.0.0.1:8000/admin/** for administration. The enrollment command displays a secret for your authenticator app and verifies a code before saving the device. Keep that secret private. At sign-in, submit your username/password, then select your authenticator device and enter a fresh code. No default admin credentials exist.

`DEBUG=true` explicitly enables local development; SQLite is supported only in that mode. Never use the development server or example environment on a public deployment. Without the required production settings, startup intentionally fails.

## Manage your watches

1. Sign in to `/admin/` with your password and current authenticator code.
2. In **Products**, create a listing with its name, unique slug, collection, USD price, real specifications, and available stock.
3. Use an HTTPS image URL hosted on an image CDN/storage service you control. The image field also accepts a relative bundled static path such as `images/watch-noir.png`. It does not upload files to Render's temporary disk.
4. Set **Active** to publish a listing and **Featured** to highlight it. Real products must have **Demo** disabled. Describe condition, provenance, warranty, and availability accurately.
5. In **Pages**, publish your business's approved policies. Text is escaped and rendered as plain paragraphs; HTML is not accepted as executable page content.
6. In **Orders**, only ship orders marked **Paid**. Use fulfillment, tracking, and staff notes to manage dispatch. Payment amounts and payment state are controlled by the payment workflow, not manually editable fields.

Stock means units currently available for purchase. Starting Checkout reserves units; confirmed canceled or expired sessions release them. Do not count reserved units a second time when editing stock. Archive sold/discontinued watches with **Active** rather than deleting products referenced by orders.

Refund payments in the Stripe Dashboard. Review the matching order after a refund webhook arrives; physical returns and restocking require your own inspection and action. The storefront does not buy postage, automatically fulfill shipments, or implement a return merchandise workflow.

## Payments and Render

Follow **[DEPLOYMENT.md](DEPLOYMENT.md)** for the full launch procedure, environment-variable table, webhook setup, and test-payment checklist.

Payment keys are entered in Render's environment settings. They are never sent to the browser. Stripe hosts card entry, so a publishable key is not needed for this redirect-based integration. Both `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET` must be configured. Never put a live key into `.env.example`, Git, a screenshot, or a support message.

## Test and maintain

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
python -m pip check
```

Run production checks using production environment values:

```bash
python manage.py check --deploy --fail-level WARNING
```

The build runs this production check and collects static files. Database migrations run in Render's pre-deploy phase. Automated tests simulate the payment boundary; they do not replace a real test-mode Checkout and webhook delivery on your deployed domain.

Keep dependencies current, review security advisories, test upgrades, back up PostgreSQL, and perform restore drills. Run `python manage.py clearsessions` on a schedule. Review Stripe's webhook delivery failures and the store's payment-review orders. For authenticator recovery, use the trusted Render Shell procedure in the deployment guide.

## Project map

| Location | Purpose |
|---|---|
| `shop/` | Catalog, shopping bag, checkout, inventory, webhooks, and order administration |
| `config/` | Environment settings, HTTP protections, two-factor admin, and platform tests |
| `templates/`, `static/` | Store design and static assets |
| `requirements.txt` | Exact resolved dependency versions |
| `.env.example` | Local-development variables only |
| `render.yaml`, `build.sh` | Render infrastructure and production build |

Implementation follows the [Django deployment checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/), [Render Django deployment documentation](https://render.com/docs/deploy-django), [Stripe webhook documentation](https://docs.stripe.com/webhooks), and [django-otp documentation](https://django-otp-official.readthedocs.io/en/stable/overview.html).
