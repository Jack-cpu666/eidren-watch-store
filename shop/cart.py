import hashlib
import json
import uuid
from decimal import Decimal

from django.conf import settings

from .models import Product, SavedCart

MAX_QUANTITY = 10
MAX_CART_PRODUCTS = 20


def normalize_quantities(raw):
    if not isinstance(raw, dict):
        return {}
    result = {}
    for key, value in list(raw.items())[:MAX_CART_PRODUCTS]:
        try:
            product_id, quantity = int(key), int(value)
        except (ValueError, TypeError):
            continue
        if product_id > 0 and 0 < quantity <= MAX_QUANTITY:
            result[str(product_id)] = quantity
    return result


def _merge_quantities(first, second):
    merged = dict(first)
    for key, quantity in second.items():
        merged[key] = min(MAX_QUANTITY, merged.get(key, 0) + quantity)
    return dict(list(merged.items())[:MAX_CART_PRODUCTS])


def cart_quantities(request):
    session_cart = normalize_quantities(request.session.get("cart", {}))
    if not request.user.is_authenticated:
        return session_cart

    saved_cart, _ = SavedCart.objects.get_or_create(user=request.user)
    saved_items = normalize_quantities(saved_cart.items)
    if session_cart:
        saved_items = _merge_quantities(saved_items, session_cart)
        saved_cart.items = saved_items
        saved_cart.save(update_fields=["items", "updated_at"])
        request.session["cart"] = {}
        request.session.modified = True
    elif saved_items != saved_cart.items:
        saved_cart.items = saved_items
        saved_cart.save(update_fields=["items", "updated_at"])
    return saved_items


def save_cart(request, quantities):
    cleaned = normalize_quantities(quantities)
    request.session["cart"] = cleaned
    request.session.modified = True
    if request.user.is_authenticated:
        SavedCart.objects.update_or_create(user=request.user, defaults={"items": cleaned})
    else:
        request.session.set_expiry(settings.CART_COOKIE_AGE)
    return cleaned


def persist_cart(request):
    """Keep an anonymous bag on this device without extending account sessions."""
    if not request.user.is_authenticated:
        request.session.set_expiry(settings.CART_COOKIE_AGE)


def get_cart(request):
    quantities = cart_quantities(request)
    products = Product.objects.filter(pk__in=quantities, is_active=True)
    items = [{"product": product, "quantity": quantities[str(product.pk)], "line_total": product.price * quantities[str(product.pk)]} for product in products]
    return {
        "items": items,
        "subtotal": sum((item["line_total"] for item in items), Decimal("0.00")),
        "total_quantity": sum(item["quantity"] for item in items),
        "contains_demo_items": any(item["product"].is_demo for item in items),
    }


def fingerprint(quantities):
    return hashlib.sha256(json.dumps(quantities, sort_keys=True).encode()).hexdigest()


def browser_key(request):
    value = request.session.get("checkout_browser_key")
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError, AttributeError):
        if not request.session.session_key:
            request.session.save()
        value = uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"{settings.SECRET_KEY}:{request.session.session_key}",
        )
        request.session["checkout_browser_key"] = str(value)
        return value
