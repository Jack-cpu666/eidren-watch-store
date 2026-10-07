import hashlib
import hmac
import json
import time
import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import stripe
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from shop.models import Order, Product, WebhookEvent
from shop.services import CheckoutProblem, apply_session, cancel_checkout, process_event, rate_limit, reconcile_order, reserve_order, start_checkout


SETTINGS = dict(
    STRIPE_SECRET_KEY="sk_test_example", STRIPE_WEBHOOK_SECRET="whsec_test_secret", SITE_URL="https://example.com",
    SHIPPING_RATE_CENTS=500, SHIPPING_COUNTRIES=["US"], STRIPE_AUTOMATIC_TAX=False,
    DEMO_MODE=False, SECURE_SSL_REDIRECT=False, ALLOWED_HOSTS=["testserver"],
)


@override_settings(**SETTINGS)
class CommerceTests(TestCase):
    def setUp(self):
        self.watch = Product.objects.create(name="Test Watch", slug="test-watch", collection="dress", price=Decimal("399.95"), stock=3, short_description="A real watch", description="Test description")
        self.key = uuid.uuid4()
        self.bag = {str(self.watch.pk): 1}

    def reserve(self):
        return reserve_order(self.key, self.bag)

    def stripe_session(self, order, status="complete", payment_status="paid", **changes):
        data = {
            "id": "cs_test_" + str(order.pk), "client_reference_id": str(order.pk), "metadata": {"order_id": str(order.pk)},
            "status": status, "payment_status": payment_status, "currency": "usd", "amount_subtotal": order.subtotal_cents,
            "amount_total": order.subtotal_cents + order.shipping_cents, "total_details": {"amount_shipping": order.shipping_cents, "amount_tax": 0, "amount_discount": 0},
            "payment_intent": "pi_test_example", "customer_details": {"email": "buyer@example.com", "name": "Test Buyer"},
            "collected_information": {"shipping_details": {"name": "Test Buyer", "address": {"line1": "1 Test Street", "country": "US"}}},
            "url": "https://checkout.stripe.com/c/pay/test" if status == "open" else None,
        }
        data.update(changes)
        return data

    def event(self, order, event_type="checkout.session.completed", event_id="evt_test_1", **session_changes):
        return {"id": event_id, "type": event_type, "livemode": False, "data": {"object": self.stripe_session(order, **session_changes)}}

    def signature(self, payload, timestamp=None):
        stamp = str(int(time.time()) if timestamp is None else timestamp)
        signed = stamp.encode() + b"." + payload
        digest = hmac.new(SETTINGS["STRIPE_WEBHOOK_SECRET"].encode(), signed, hashlib.sha256).hexdigest()
        return f"t={stamp},v1={digest}"

    def test_reservation_uses_database_prices_and_reuses_existing_order(self):
        order = self.reserve()
        self.assertEqual(order.subtotal_cents, 39995)
        self.assertEqual(order.checkout_payload["line_items"][0]["price_data"]["unit_amount"], 39995)
        self.assertEqual(reserve_order(self.key, self.bag).pk, order.pk)
        self.watch.refresh_from_db()
        self.assertEqual(self.watch.stock, 2)
        self.assertEqual(Order.objects.count(), 1)

    def test_sold_out_inventory_cannot_be_reserved_again(self):
        Product.objects.filter(pk=self.watch.pk).update(stock=1)
        self.reserve()
        with self.assertRaises(CheckoutProblem):
            reserve_order(uuid.uuid4(), self.bag)
        self.watch.refresh_from_db()
        self.assertEqual(self.watch.stock, 0)
        self.assertEqual(Order.objects.count(), 1)

    def test_multiple_line_reservation_rolls_back_when_one_unavailable(self):
        second = Product.objects.create(name="Sold out", slug="sold-out", collection="dive", price=100, stock=0)
        with self.assertRaises(CheckoutProblem):
            reserve_order(self.key, {str(self.watch.pk): 1, str(second.pk): 1})
        self.watch.refresh_from_db()
        self.assertEqual(self.watch.stock, 3)
        self.assertEqual(Order.objects.count(), 0)

    def test_changed_bag_requires_existing_checkout_cancellation(self):
        self.reserve()
        with self.assertRaises(CheckoutProblem):
            reserve_order(self.key, {str(self.watch.pk): 2})
        self.assertEqual(Order.objects.count(), 1)

    def test_demo_cannot_be_purchased_with_live_keys_even_in_debug(self):
        self.watch.is_demo = True
        self.watch.save()
        with override_settings(DEBUG=True, DEMO_MODE=True, STRIPE_SECRET_KEY="sk_live_example"):
            with self.assertRaises(CheckoutProblem):
                self.reserve()
        self.watch.refresh_from_db()
        self.assertEqual(self.watch.stock, 3)

    def test_demo_disabled_in_production(self):
        self.watch.is_demo = True
        self.watch.save()
        with override_settings(DEBUG=False, DEMO_MODE=False):
            with self.assertRaises(CheckoutProblem):
                self.reserve()

    def test_checkout_post_ignores_client_supplied_price(self):
        session = self.client.session
        session["cart"] = self.bag
        session.save()
        def fake_create(**kwargs):
            order = Order.objects.get(pk=kwargs["metadata"]["order_id"])
            self.assertEqual(kwargs["line_items"][0]["price_data"]["unit_amount"], 39995)
            return self.stripe_session(order, status="open", payment_status="unpaid")
        with patch("shop.services.stripe.checkout.Session.create", side_effect=fake_create) as create:
            response = self.client.post(reverse("shop:checkout"), {"price": "0.01", "total": "0.01"})
        self.assertEqual(response.status_code, 303)
        self.assertEqual(Order.objects.get().subtotal_cents, 39995)
        self.assertEqual(create.call_count, 1)

    def test_ambiguous_create_failure_preserves_inventory_and_idempotency(self):
        with patch("shop.services.stripe.checkout.Session.create", side_effect=stripe.APIConnectionError("timeout")) as create:
            for _ in range(2):
                with self.assertRaises(CheckoutProblem):
                    start_checkout(self.key, self.bag)
        self.assertEqual(create.call_args_list[0].kwargs["idempotency_key"], create.call_args_list[1].kwargs["idempotency_key"])
        self.assertEqual(create.call_args_list[0].kwargs, create.call_args_list[1].kwargs)
        self.watch.refresh_from_db()
        self.assertEqual(self.watch.stock, 2)
        self.assertEqual(Order.objects.count(), 1)

    def test_signed_webhook_settles_once_and_preserves_reserved_stock(self):
        order = self.reserve()
        payload = json.dumps(self.event(order)).encode()
        for _ in range(2):
            response = self.client.post(reverse("shop:stripe_webhook"), data=payload, content_type="application/json", HTTP_STRIPE_SIGNATURE=self.signature(payload))
            self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.watch.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAID)
        self.assertEqual(order.shipping_address["country"], "US")
        self.assertEqual(self.watch.stock, 2)
        self.assertEqual(WebhookEvent.objects.count(), 1)

    def test_forged_and_stale_webhook_signatures_do_not_settle(self):
        order = self.reserve()
        payload = json.dumps(self.event(order)).encode()
        for sig in ("t=1,v1=forged", self.signature(payload, int(time.time()) - 600)):
            response = self.client.post(reverse("shop:stripe_webhook"), data=payload, content_type="application/json", HTTP_STRIPE_SIGNATURE=sig)
            self.assertEqual(response.status_code, 400)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertFalse(WebhookEvent.objects.exists())

    def test_wrong_currency_or_amount_requires_manual_review(self):
        order = self.reserve()
        apply_session(self.stripe_session(order, currency="eur"))
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.REVIEW)
        self.assertIsNone(order.paid_at)
        self.watch.refresh_from_db()
        self.assertEqual(self.watch.stock, 2)

    def test_unpaid_completed_session_is_not_fulfilled(self):
        order = self.reserve()
        apply_session(self.stripe_session(order, payment_status="unpaid"))
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PENDING)

    def test_expired_checkout_releases_stock_exactly_once(self):
        order = self.reserve()
        for event_id in ("evt_expire_1", "evt_expire_2"):
            process_event(self.event(order, event_type="checkout.session.expired", event_id=event_id, status="expired", payment_status="unpaid"))
        order.refresh_from_db()
        self.watch.refresh_from_db()
        self.assertEqual(order.status, Order.Status.EXPIRED)
        self.assertEqual(self.watch.stock, 3)

    def test_expiry_after_paid_does_not_restore_inventory(self):
        order = self.reserve()
        apply_session(self.stripe_session(order))
        apply_session(self.stripe_session(order, status="expired", payment_status="unpaid"))
        order.refresh_from_db()
        self.watch.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAID)
        self.assertEqual(self.watch.stock, 2)

    def test_unknown_checkout_cannot_release_inventory_on_cancel(self):
        self.reserve()
        with self.assertRaises(CheckoutProblem):
            cancel_checkout(self.key)
        self.watch.refresh_from_db()
        self.assertEqual(self.watch.stock, 2)

    def test_reconciliation_recovers_session_after_worker_crash(self):
        order = self.reserve()
        listed = MagicMock()
        listed.auto_paging_iter.return_value = iter([self.stripe_session(order)])
        with patch("shop.services.stripe.checkout.Session.list", return_value=listed):
            status = reconcile_order(order)
        self.assertEqual(status, Order.Status.PAID)
        self.assertTrue(order.stripe_session_id)

    def test_reconciliation_releases_proven_absent_session_only_after_expiry(self):
        order = self.reserve()
        listed = MagicMock()
        listed.auto_paging_iter.side_effect = lambda: iter([])
        with patch("shop.services.stripe.checkout.Session.list", return_value=listed):
            self.assertEqual(reconcile_order(order), Order.Status.PENDING)
            order.reserved_until = timezone.now() - timedelta(minutes=6)
            order.save(update_fields=["reserved_until"])
            self.assertEqual(reconcile_order(order), Order.Status.EXPIRED)
        self.watch.refresh_from_db()
        self.assertEqual(self.watch.stock, 3)

    def test_reconciliation_network_failure_keeps_inventory(self):
        order = self.reserve()
        with patch("shop.services.stripe.checkout.Session.list", side_effect=stripe.APIConnectionError("timeout")):
            with self.assertRaises(stripe.APIConnectionError):
                reconcile_order(order)
        self.watch.refresh_from_db()
        self.assertEqual(self.watch.stock, 2)

    def test_cart_mutations_require_post_and_csrf(self):
        client = Client(enforce_csrf_checks=True)
        url = reverse("shop:cart_add", args=[self.watch.pk])
        self.assertEqual(client.get(url).status_code, 405)
        self.assertEqual(client.post(url, {"quantity": 1}).status_code, 403)
        self.assertEqual(client.post(reverse("shop:checkout")).status_code, 403)

    def test_cart_rejects_invalid_quantity_and_open_redirect(self):
        url = reverse("shop:cart_add", args=[self.watch.pk])
        for quantity in ("-2", "1000000", "nonsense"):
            response = self.client.post(url, {"quantity": quantity, "next": "https://evil.example"})
            self.assertRedirects(response, reverse("shop:cart"), fetch_redirect_response=False)
        self.assertEqual(self.client.session.get("cart", {}), {})

    def test_limiter_is_persistent(self):
        self.assertTrue(rate_limit("checkout-test", limit=2))
        self.assertTrue(rate_limit("checkout-test", limit=2))
        self.assertFalse(rate_limit("checkout-test", limit=2))

    def test_full_refund_does_not_automatically_restock_returns(self):
        order = self.reserve()
        process_event(self.event(order))
        process_event({"id": "evt_refund", "type": "charge.refunded", "livemode": False, "data": {"object": {"refunded": True, "payment_intent": "pi_test_example"}}})
        order.refresh_from_db()
        self.watch.refresh_from_db()
        self.assertEqual(order.status, Order.Status.REFUNDED)
        self.assertEqual(self.watch.stock, 2)

    def test_staff_cannot_directly_change_payment_status(self):
        from shop.admin import OrderAdmin
        self.assertIn("status", OrderAdmin.readonly_fields)
        self.assertIn("stripe_payment_intent", OrderAdmin.readonly_fields)

    def test_redirect_cannot_confirm_payment_or_expose_another_visitors_order(self):
        order = self.reserve()
        stripe_obj = self.stripe_session(order, status="open", payment_status="unpaid")
        order.stripe_session_id = stripe_obj["id"]
        order.save(update_fields=["stripe_session_id"])
        with patch("shop.views.render", return_value=__import__("django.http", fromlist=["HttpResponse"]).HttpResponse()) as render:
            response = self.client.get(reverse("shop:checkout_success"), {"session_id": stripe_obj["id"]})
            self.assertEqual(response.status_code, 200)
            self.assertIsNone(render.call_args.args[2]["order"])
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PENDING)
