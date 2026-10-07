import hashlib
import json
import uuid
from decimal import Decimal

from django.conf import settings

from .models import Product

MAX_QUANTITY = 10
MAX_CART_PRODUCTS = 20


def cart_quantities(request):
    raw = request.session.get("cart", {})
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


def get_cart(request):
    quantities = cart_quantities(request)
    products = Product.objects.filter(pk__in=quantities, is_active=True)
    items = [{"product": product, "quantity": quantities[str(product.pk)], "line_total": product.price * quantities[str(product.pk)]} for product in products]
    return {
        "items": items,
        "subtotal": sum((item["line_total"] for item in items), Decimal("0.00")),
        "total_quantity": sum(item["quantity"] for item in items),
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
