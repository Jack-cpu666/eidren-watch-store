import logging

import stripe
from django.conf import settings
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import connection
from django.db.models import Q
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .cart import MAX_CART_PRODUCTS, MAX_QUANTITY, browser_key, cart_quantities, fingerprint, get_cart
from .models import CheckoutState, Order, Page, Product
from .services import CheckoutProblem, PaymentMismatch, cancel_checkout, process_event, rate_limit, start_checkout

logger = logging.getLogger(__name__)


@require_GET
def home(request):
    return render(request, "shop/home.html", {"featured_products": Product.objects.filter(is_active=True, is_featured=True)[:4]})


@require_GET
def catalog(request):
    products = Product.objects.filter(is_active=True)
    query = request.GET.get("q", "").strip()[:120]
    selected_collection = request.GET.get("collection", "")
    if query:
        products = products.filter(Q(name__icontains=query) | Q(brand__icontains=query) | Q(short_description__icontains=query))
    if selected_collection in Product.Collection.values:
        products = products.filter(collection=selected_collection)
    else:
        selected_collection = ""
    sort = request.GET.get("sort", "featured")
    ordering = {"featured": ["-is_featured", "name"], "price_asc": ["price", "name"], "price_desc": ["-price", "name"], "newest": ["-created_at", "name"]}
    if sort not in ordering:
        sort = "featured"
    page_obj = Paginator(products.order_by(*ordering[sort]), 12).get_page(request.GET.get("page"))
    return render(request, "shop/catalog.html", {"products": page_obj, "page_obj": page_obj, "paginator": page_obj.paginator, "query": query, "selected_collection": selected_collection, "sort": sort, "collections": Product.Collection.choices})


@require_GET
def product_detail(request, slug):
    product = get_object_or_404(Product, slug=slug, is_active=True)
    related = Product.objects.filter(is_active=True).exclude(pk=product.pk).order_by("-is_featured", "name")[:3]
    return render(request, "shop/product_detail.html", {"product": product, "related_products": related})


@never_cache
@require_GET
def cart(request):
    browser_key(request)
    active_order = None
    key = request.session.get("checkout_browser_key")
    if key:
        state = CheckoutState.objects.select_related("current_order").filter(pk=key).first()
        if state and state.current_order and state.current_order.status == Order.Status.PENDING:
            active_order = state.current_order
    return render(request, "shop/cart.html", {"cart": get_cart(request), "active_order": active_order})


def _quantity(request):
    try:
        raw = request.POST.get("quantity", "1")
        if len(raw) > 3:
            raise ValueError
        quantity = int(raw)
        if not 0 <= quantity <= MAX_QUANTITY:
            raise ValueError
        return quantity
    except (TypeError, ValueError):
        return None


@require_POST
def cart_add(request, product_id):
    product = get_object_or_404(Product, pk=product_id, is_active=True)
    quantity = _quantity(request)
    quantities = cart_quantities(request)
    existing = quantities.get(str(product.pk), 0)
    if quantity is None or quantity == 0:
        messages.error(request, f"Choose a quantity between 1 and {MAX_QUANTITY}.")
    elif str(product.pk) not in quantities and len(quantities) >= MAX_CART_PRODUCTS:
        messages.error(request, "Your bag has reached the maximum number of different watches.")
    elif existing + quantity > min(product.stock, MAX_QUANTITY):
        messages.error(request, "That quantity is not currently available. Please check your bag.")
    else:
        quantities[str(product.pk)] = existing + quantity
        request.session["cart"] = quantities
        messages.success(request, f"{product.name} has been added to your bag.")
    # Never redirect to an arbitrary user-provided URL.
    return redirect(product if request.POST.get("next") == "product" else "shop:cart")


@require_POST
def cart_update(request, product_id):
    quantities = cart_quantities(request)
    quantity = _quantity(request)
    product = Product.objects.filter(pk=product_id, is_active=True).first()
    if quantity == 0 or product is None:
        quantities.pop(str(product_id), None)
    elif quantity is None:
        messages.error(request, f"Choose a quantity between 0 and {MAX_QUANTITY}.")
    elif quantity > product.stock:
        messages.error(request, "That quantity is not currently available. An open checkout may already be holding your watches.")
    elif str(product_id) in quantities:
        quantities[str(product_id)] = quantity
    request.session["cart"] = quantities
    return redirect("shop:cart")


@require_POST
def cart_remove(request, product_id):
    quantities = cart_quantities(request)
    quantities.pop(str(product_id), None)
    request.session["cart"] = quantities
    return redirect("shop:cart")


@never_cache
@require_POST
def checkout(request):
    identity = str(browser_key(request))
    ip = request.META.get("REMOTE_ADDR", "unknown")
    if not rate_limit("checkout-ip:" + ip, limit=30) or not rate_limit("checkout-browser:" + identity):
        return HttpResponse("Too many checkout attempts. Please wait 15 minutes and try again.", status=429, headers={"Retry-After": "900"})
    try:
        order, url = start_checkout(identity, cart_quantities(request))
    except CheckoutProblem as exc:
        messages.error(request, str(exc))
        return redirect("shop:cart")
    except PaymentMismatch:
        logger.exception("Checkout session mismatch")
        messages.error(request, "We could not verify this payment session. Please contact the store; no new payment has been started.")
        return redirect("shop:cart")
    if url:
        return HttpResponse(status=303, headers={"Location": url})
    return redirect("shop:checkout_success")


@never_cache
@require_POST
def checkout_cancel(request):
    try:
        cancel_checkout(browser_key(request))
        messages.success(request, "Your unpaid checkout has been canceled. Your bag is ready to edit.")
    except CheckoutProblem as exc:
        messages.error(request, str(exc))
    return redirect("shop:cart")


@never_cache
@require_GET
def checkout_success(request):
    # A redirect is not proof of payment. Only show state written by a signed
    # webhook or authenticated reconciliation, and require the visitor's session.
    order = None
    key = request.session.get("checkout_browser_key")
    if key:
        orders = Order.objects.filter(browser_key=key).prefetch_related("items")
        stripe_id = request.GET.get("session_id", "")
        order = orders.filter(stripe_session_id=stripe_id).first() if stripe_id else orders.first()
    if order and order.status == Order.Status.PAID and fingerprint(cart_quantities(request)) == order.cart_fingerprint:
        request.session["cart"] = {}
    return render(request, "shop/checkout_success.html", {"order": order})


@require_GET
def page(request, slug):
    obj = get_object_or_404(Page, slug=slug, is_published=True)
    return render(request, "shop/page.html", {"page": obj})


@require_GET
def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ok"})


@csrf_exempt
@require_POST
def stripe_webhook(request):
    if not settings.STRIPE_WEBHOOK_SECRET:
        return HttpResponse(status=503)
    if len(request.body) > 256_000:
        return HttpResponseBadRequest("Invalid payload.")
    try:
        event = stripe.Webhook.construct_event(request.body, request.META.get("HTTP_STRIPE_SIGNATURE", ""), settings.STRIPE_WEBHOOK_SECRET, tolerance=300)
    except (ValueError, stripe.SignatureVerificationError):
        return HttpResponseBadRequest("Invalid signature.")
    try:
        process_event(event)
    except PaymentMismatch:
        logger.exception("Rejected mismatched Stripe webhook")
        return HttpResponseBadRequest("Payment verification failed.")
    return HttpResponse(status=200)
