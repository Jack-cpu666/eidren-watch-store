from decimal import Decimal

from django.conf import settings

from .cart import cart_quantities


def store_context(request):
    return {
        "store_name": settings.STORE_NAME,
        "store_email": settings.STORE_EMAIL,
        "cart_count": sum(cart_quantities(request).values()),
        "payments_enabled": bool(settings.STRIPE_SECRET_KEY and settings.STRIPE_WEBHOOK_SECRET),
        "demo_mode": settings.DEMO_MODE,
        "shipping_rate": Decimal(settings.SHIPPING_RATE_CENTS) / 100,
        "shipping_countries": settings.SHIPPING_COUNTRIES,
    }
