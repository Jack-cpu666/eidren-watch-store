"""Payment boundaries: trusted prices, committed reservations and verified settlement.

Stock means available stock and is removed at reservation time. An uncertain API
result must never put those units back on sale. Only a verified expired session,
or reconciliation that finds no session after its creation window, releases it.
"""
import hashlib
import hmac
import logging
from datetime import timedelta

import stripe
from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.urls import reverse
from django.utils import timezone

from .cart import MAX_CART_PRODUCTS, MAX_QUANTITY, fingerprint
from .models import CheckoutState, Order, OrderItem, Product, RateLimitBucket, WebhookEvent

logger = logging.getLogger(__name__)


class CheckoutProblem(Exception):
    pass


class PaymentMismatch(Exception):
    pass


def rate_limit(identity, limit=12, seconds=900):
    """Database-backed limiter; multiple web workers share the same counter."""
    key = hmac.new(settings.SECRET_KEY.encode(), identity.encode(), hashlib.sha256).hexdigest()
    now = timezone.now()
    RateLimitBucket.objects.get_or_create(key=key, defaults={"window_started": now})
    with transaction.atomic():
        bucket = RateLimitBucket.objects.select_for_update().get(pk=key)
        if bucket.window_started <= now - timedelta(seconds=seconds):
            bucket.window_started, bucket.count = now, 0
        bucket.count += 1
        bucket.save(update_fields=["window_started", "count"])
        return bucket.count <= limit


def _checkout_payload(order, items):
    origin = settings.SITE_URL.rstrip("/")
    payload = {
        "mode": "payment",
        "payment_method_types": ["card"],
        "client_reference_id": str(order.id),
        "metadata": {"order_id": str(order.id)},
        "payment_intent_data": {"metadata": {"order_id": str(order.id)}},
        "success_url": origin + reverse("shop:checkout_success") + "?session_id={CHECKOUT_SESSION_ID}",
        "cancel_url": origin + reverse("shop:cart") + "?checkout=canceled",
        "expires_at": int(order.reserved_until.timestamp()),
        "billing_address_collection": "required",
        "shipping_address_collection": {"allowed_countries": settings.SHIPPING_COUNTRIES},
        "shipping_options": [{"shipping_rate_data": {
            "type": "fixed_amount", "fixed_amount": {"amount": order.shipping_cents, "currency": "usd"},
            "display_name": "Standard shipping", "tax_behavior": "exclusive",
        }}],
        "automatic_tax": {"enabled": settings.STRIPE_AUTOMATIC_TAX},
        "line_items": [],
    }
    for item in items:
        payload["line_items"].append({
            "price_data": {
                "currency": "usd", "unit_amount": item.unit_price_cents, "tax_behavior": "exclusive",
                "product_data": {"name": item.product_name, "metadata": {"product_id": str(item.product_id)}},
            },
            "quantity": item.quantity,
        })
    return payload


def reserve_order(browser_key, quantities, customer=None):
    if not quantities or len(quantities) > MAX_CART_PRODUCTS:
        raise CheckoutProblem("Your bag is empty. Add a watch before checking out.")
    if any(not str(key).isdigit() or type(qty) is not int or not 1 <= qty <= MAX_QUANTITY for key, qty in quantities.items()):
        raise CheckoutProblem("Please check the quantities in your bag.")
    CheckoutState.objects.get_or_create(browser_key=browser_key)
    with transaction.atomic():
        state = CheckoutState.objects.select_for_update().get(pk=browser_key)
        if state.current_order_id:
            current = Order.objects.select_for_update().get(pk=state.current_order_id)
            if current.status == Order.Status.PENDING:
                if current.cart_fingerprint != fingerprint(quantities):
                    raise CheckoutProblem("Your previous checkout still holds its watches. Cancel that checkout below before paying for your updated bag.")
                if customer and current.customer_id is None:
                    current.customer = customer
                    current.save(update_fields=["customer", "updated_at"])
                return current
        products = list(Product.objects.select_for_update().filter(pk__in=quantities).order_by("pk"))
        if len(products) != len(quantities):
            raise CheckoutProblem("A watch in your bag is no longer available. Please update your bag.")
        subtotal = 0
        for product in products:
            quantity = quantities[str(product.pk)]
            if not product.is_active or product.stock < quantity:
                raise CheckoutProblem(f"{product.name} no longer has that quantity available. Please update your bag.")
            if product.is_demo:
                raise CheckoutProblem("Preview watches can be saved in your bag, but cannot be checked out. Replace them with verified inventory before accepting payments.")
            subtotal += product.price_cents * quantity
        # Stripe accepts expirations at least 30 minutes away. A minute of margin
        # allows for the DB commit and ordinary network latency.
        order = Order.objects.create(
            browser_key=browser_key, customer=customer, cart_fingerprint=fingerprint(quantities),
            subtotal_cents=subtotal, shipping_cents=settings.SHIPPING_RATE_CENTS,
            total_cents=subtotal + settings.SHIPPING_RATE_CENTS,
            reserved_until=timezone.now() + timedelta(minutes=31),
        )
        items = []
        for product in products:
            quantity = quantities[str(product.pk)]
            changed = Product.objects.filter(pk=product.pk, stock__gte=quantity).update(stock=F("stock") - quantity)
            if changed != 1:
                raise CheckoutProblem("One of these watches just sold. Please update your bag.")
            items.append(OrderItem(order=order, product=product, product_name=product.name, unit_price_cents=product.price_cents, quantity=quantity))
        OrderItem.objects.bulk_create(items)
        order.checkout_payload = _checkout_payload(order, items)
        order.save(update_fields=["checkout_payload"])
        state.current_order = order
        state.save(update_fields=["current_order", "updated_at"])
        return order


def attach_session(order, session):
    session_id = session.get("id", "")
    if not session_id or session.get("client_reference_id") != str(order.id):
        raise PaymentMismatch("Checkout session does not match the reserved order.")
    with transaction.atomic():
        locked = Order.objects.select_for_update().get(pk=order.pk)
        if locked.stripe_session_id and locked.stripe_session_id != session_id:
            raise PaymentMismatch("An order may only have one Stripe Checkout Session.")
        locked.stripe_session_id = session_id
        locked.stripe_checkout_url = session.get("url") or ""
        locked.save(update_fields=["stripe_session_id", "stripe_checkout_url", "updated_at"])
    order.stripe_session_id = session_id
    order.stripe_checkout_url = session.get("url") or ""


def start_checkout(browser_key, quantities, customer=None):
    if not settings.STRIPE_SECRET_KEY or not settings.STRIPE_WEBHOOK_SECRET:
        raise CheckoutProblem("Online checkout is being configured. Please contact the store for assistance.")
    order = reserve_order(browser_key, quantities, customer=customer)
    try:
        if order.stripe_session_id:
            session = stripe.checkout.Session.retrieve(order.stripe_session_id, api_key=settings.STRIPE_SECRET_KEY)
        else:
            if order.reserved_until <= timezone.now() + timedelta(seconds=30):
                raise CheckoutProblem("This checkout needs to be reconciled before its watches can be released. Please try again after the store has reconciled payments.")
            session = stripe.checkout.Session.create(
                **order.checkout_payload, idempotency_key=f"eidren-order-{order.pk}", api_key=settings.STRIPE_SECRET_KEY,
            )
        attach_session(order, session)
        apply_session(session)
        order.refresh_from_db()
        if order.status == Order.Status.PAID:
            return order, None
        if order.status == Order.Status.EXPIRED:
            # Inventory has been returned only after Stripe confirms expiration.
            raise CheckoutProblem("That checkout expired. Your bag is ready; select checkout again to start a new payment.")
        if order.status != Order.Status.PENDING or session.get("status") != "open" or not session.get("url"):
            raise CheckoutProblem("Your payment is being verified. Please check the confirmation page or contact the store.")
        return order, session["url"]
    except stripe.StripeError:
        # Even a timeout can happen after Stripe accepted the creation. Retain
        # inventory, and retry the same immutable request with its idempotency key.
        logger.warning("Stripe checkout request failed; inventory retained for order %s", order.pk)
        raise CheckoutProblem("The payment service is temporarily unavailable. Your watches remain reserved; retry checkout to continue the same payment.") from None


def _release_locked(order):
    if order.status != Order.Status.PENDING:
        return False
    for item in order.items.order_by("product_id"):
        Product.objects.filter(pk=item.product_id).update(stock=F("stock") + item.quantity)
    order.status = Order.Status.EXPIRED
    order.stripe_checkout_url = ""
    order.save(update_fields=["status", "stripe_checkout_url", "updated_at"])
    return True


def apply_session(session):
    """Called only with authenticated Stripe API results or signed webhooks."""
    order_id = (session.get("metadata") or {}).get("order_id") or session.get("client_reference_id")
    if not order_id:
        return None
    try:
        with transaction.atomic():
            order = Order.objects.select_for_update().filter(pk=order_id).first()
            if order is None:
                return None
            if session.get("client_reference_id") != str(order.pk):
                raise PaymentMismatch("Invalid checkout reference.")
            if order.stripe_session_id and order.stripe_session_id != session.get("id"):
                raise PaymentMismatch("Checkout session ID mismatch.")
            if not order.stripe_session_id:
                order.stripe_session_id = session["id"]
                order.save(update_fields=["stripe_session_id"])
            if session.get("status") == "expired":
                _release_locked(order)
                return order
            if session.get("payment_status") != "paid":
                return order
            if order.status in (Order.Status.PAID, Order.Status.REFUNDED):
                return order
            details = session.get("total_details") or {}
            shipping = details.get("amount_shipping", 0)
            tax = details.get("amount_tax", 0)
            valid = (
                session.get("currency") == order.currency
                and session.get("amount_subtotal") == order.subtotal_cents
                and shipping == order.shipping_cents
                and isinstance(tax, int) and tax >= 0
                and details.get("amount_discount", 0) == 0
                and session.get("amount_total") == order.subtotal_cents + shipping + tax
                and session.get("status") == "complete"
                and order.status == Order.Status.PENDING
            )
            if not valid:
                order.status = Order.Status.REVIEW
                order.save(update_fields=["status", "updated_at"])
                logger.error("Payment requires manual review for order %s: totals or state mismatch", order.pk)
                return order
            customer = session.get("customer_details") or {}
            shipping_details = (session.get("collected_information") or {}).get("shipping_details") or session.get("shipping_details") or {}
            order.customer_email = (customer.get("email") or "")[:254]
            order.customer_name = (shipping_details.get("name") or customer.get("name") or "")[:240]
            order.shipping_address = shipping_details.get("address") or {}
            order.stripe_payment_intent = session.get("payment_intent") or ""
            if isinstance(order.stripe_payment_intent, dict):
                order.stripe_payment_intent = order.stripe_payment_intent.get("id", "")
            order.tax_cents = tax
            order.total_cents = session["amount_total"]
            order.status = Order.Status.PAID
            order.paid_at = timezone.now()
            order.stripe_checkout_url = ""
            order.save()
            return order
    except (ValueError, TypeError):
        raise PaymentMismatch("Malformed checkout order reference.") from None


def process_event(event):
    event_id = event.get("id", "")
    if not event_id:
        raise PaymentMismatch("Missing Stripe event ID.")
    expected_live = settings.STRIPE_SECRET_KEY.startswith(("sk_live_", "rk_live_"))
    if bool(event.get("livemode")) != expected_live:
        raise PaymentMismatch("Stripe event mode does not match this store.")
    with transaction.atomic():
        record, created = WebhookEvent.objects.get_or_create(stripe_id=event_id, defaults={"event_type": event["type"]})
        if not created:
            return
        obj = event["data"]["object"]
        if event["type"] in ("checkout.session.completed", "checkout.session.async_payment_succeeded", "checkout.session.expired"):
            apply_session(obj)
        elif event["type"] == "charge.refunded" and obj.get("refunded"):
            intent = obj.get("payment_intent")
            # Refunds are initiated in Stripe; returned merchandise must be
            # inspected before an administrator adds it back to available stock.
            if intent:
                Order.objects.filter(stripe_payment_intent=intent, status=Order.Status.PAID).update(status=Order.Status.REFUNDED)


def cancel_checkout(browser_key):
    state = CheckoutState.objects.filter(pk=browser_key).first()
    if not state or not state.current_order_id:
        return
    order = Order.objects.get(pk=state.current_order_id)
    if order.status != Order.Status.PENDING:
        return
    if not order.stripe_session_id:
        raise CheckoutProblem("This payment request is still being reconciled. Retry your original checkout or contact the store; its inventory is held safely.")
    try:
        session = stripe.checkout.Session.retrieve(order.stripe_session_id, api_key=settings.STRIPE_SECRET_KEY)
        if session.get("status") == "open":
            try:
                session = stripe.checkout.Session.expire(order.stripe_session_id, api_key=settings.STRIPE_SECRET_KEY)
            except stripe.InvalidRequestError:
                # The customer may have paid between retrieve and expire.
                session = stripe.checkout.Session.retrieve(order.stripe_session_id, api_key=settings.STRIPE_SECRET_KEY)
        apply_session(session)
        order.refresh_from_db()
        if order.status == Order.Status.PAID:
            raise CheckoutProblem("This order was already paid. It cannot be canceled here; contact the store about a refund.")
        if order.status != Order.Status.EXPIRED:
            raise CheckoutProblem("Payment is being processed. Your reservation stays in place until its status is confirmed.")
    except stripe.StripeError:
        raise CheckoutProblem("The payment service could not confirm cancellation. Please retry shortly; your reservation is still protected.") from None


def reconcile_order(order):
    if order.status != Order.Status.PENDING:
        return order.status
    if order.stripe_session_id:
        session = stripe.checkout.Session.retrieve(order.stripe_session_id, api_key=settings.STRIPE_SECRET_KEY)
        apply_session(session)
    else:
        # This handles a worker dying after Stripe created a Session but before
        # its ID was saved. Fully page through this order's creation window.
        matches = []
        result = stripe.checkout.Session.list(
            created={"gte": int(order.created_at.timestamp()) - 60, "lte": int(order.reserved_until.timestamp()) + 60},
            limit=100, api_key=settings.STRIPE_SECRET_KEY,
        )
        for session in result.auto_paging_iter():
            if (session.get("metadata") or {}).get("order_id") == str(order.pk):
                matches.append(session)
        if len(matches) > 1:
            raise PaymentMismatch("Multiple sessions found for one order; manual reconciliation required.")
        if matches:
            attach_session(order, matches[0])
            apply_session(matches[0])
        elif timezone.now() > order.reserved_until + timedelta(minutes=5):
            # No Stripe Session exists and the fixed expires_at in the immutable
            # payload can no longer create a payable Session. Release under lock.
            with transaction.atomic():
                locked = Order.objects.select_for_update().get(pk=order.pk)
                if not locked.stripe_session_id:
                    _release_locked(locked)
    order.refresh_from_db()
    return order.status
