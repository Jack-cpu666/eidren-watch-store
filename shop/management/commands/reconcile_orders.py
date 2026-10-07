from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from shop.models import Order, RateLimitBucket
from shop.services import reconcile_order


class Command(BaseCommand):
    help = "Verify pending orders with Stripe, recover missing session IDs, and release only confirmed expired or absent checkouts. Run every 5 minutes."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=500)

    def handle(self, *args, **options):
        if not settings.STRIPE_SECRET_KEY:
            raise CommandError("STRIPE_SECRET_KEY must be configured for payment reconciliation.")
        limit = max(1, min(options["limit"], 5000))
        failures = 0
        for order in Order.objects.filter(status=Order.Status.PENDING).order_by("created_at")[:limit]:
            try:
                status = reconcile_order(order)
                self.stdout.write(f"{order.reference}: {status}")
            except Exception as exc:
                failures += 1
                # Do not emit payment payloads, addresses, or credentials.
                self.stderr.write(f"{order.reference}: reconciliation failed ({type(exc).__name__}); reservation retained.")
        RateLimitBucket.objects.filter(window_started__lt=timezone.now() - timedelta(days=2)).delete()
        if failures:
            raise CommandError(f"{failures} order(s) could not be reconciled. Review service logs and retry.")
        self.stdout.write(self.style.SUCCESS("Payment reconciliation complete."))
