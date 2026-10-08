import logging

import stripe
from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import connection
from django.db.models import Q
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .cart import MAX_CART_PRODUCTS, MAX_QUANTITY, browser_key, cart_quantities, fingerprint, get_cart, persist_cart, save_cart
from .models import CheckoutState, Order, Page, Product
from .services import CheckoutProblem, PaymentMismatch, cancel_checkout, process_event, rate_limit, start_checkout

logger = logging.getLogger(__name__)


class CustomerSignUpForm(UserCreationForm):
    email = forms.EmailField(required=True, help_text="Used for order updates and to identify your account.")
    accept_terms = forms.BooleanField(required=True, label="I agree to the Terms of sale and acknowledge the Privacy notice.")

    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ("username", "email", "password1", "password2")

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if get_user_model().objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account already uses this email address. Please sign in instead.")
        return email


def _safe_next(request, fallback="shop:account"):
    candidate = request.POST.get("next") or request.GET.get("next")
    if candidate and url_has_allowed_host_and_scheme(candidate, {request.get_host()}, require_https=request.is_secure()):
        return candidate
    return fallback


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
    persist_cart(request)
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
        save_cart(request, quantities)
        messages.success(request, f"{product.name} has been saved to your bag." if product.is_demo else f"{product.name} has been added to your bag.")
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
    save_cart(request, quantities)
    return redirect("shop:cart")


@require_POST
def cart_remove(request, product_id):
    quantities = cart_quantities(request)
    quantities.pop(str(product_id), None)
    save_cart(request, quantities)
    return redirect("shop:cart")


@never_cache
@require_POST
def checkout(request):
    identity = str(browser_key(request))
    ip = request.META.get("REMOTE_ADDR", "unknown")
    if not rate_limit("checkout-ip:" + ip, limit=30) or not rate_limit("checkout-browser:" + identity):
        return HttpResponse("Too many checkout attempts. Please wait 15 minutes and try again.", status=429, headers={"Retry-After": "900"})
    cart = get_cart(request)
    if cart["contains_demo_items"]:
        messages.error(request, "Preview watches can be saved in your bag but cannot be checked out. Publish verified inventory to accept payments.")
        return redirect("shop:cart")
    if request.POST.get("accept_terms") != "yes":
        messages.error(request, "Please agree to the Terms of sale and acknowledge the Privacy notice before checkout.")
        return redirect("shop:cart")
    try:
        customer = request.user if request.user.is_authenticated else None
        order, url = start_checkout(identity, cart_quantities(request), customer=customer)
        order.terms_accepted_at = timezone.now()
        order.save(update_fields=["terms_accepted_at", "updated_at"])
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
        save_cart(request, {})
    return render(request, "shop/checkout_success.html", {"order": order})


@require_GET
def page(request, slug):
    obj = get_object_or_404(Page, slug=slug, is_published=True)
    return render(request, "shop/page.html", {"page": obj})


@never_cache
def account_login(request):
    if request.user.is_authenticated:
        return redirect(_safe_next(request))
    form = AuthenticationForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        login(request, form.get_user())
        cart_quantities(request)  # Merge the device bag into the account bag.
        messages.success(request, "Welcome back. Your saved bag is ready.")
        return redirect(_safe_next(request))
    return render(request, "shop/account_auth.html", {"form": form, "mode": "login", "next": request.GET.get("next", "")})


@never_cache
def account_register(request):
    if request.user.is_authenticated:
        return redirect("shop:account")
    if request.method == "POST" and not rate_limit("account-register:" + request.META.get("REMOTE_ADDR", "unknown"), limit=10, seconds=3600):
        return HttpResponse("Too many account creation attempts. Please try again later.", status=429, headers={"Retry-After": "3600"})
    form = CustomerSignUpForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        user.email = form.cleaned_data["email"]
        user.save(update_fields=["email"])
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        cart_quantities(request)  # Merge the device bag into the newly created account bag.
        messages.success(request, "Your account is ready. Your bag will now follow you across devices.")
        return redirect(_safe_next(request))
    return render(request, "shop/account_auth.html", {"form": form, "mode": "register", "next": request.GET.get("next", "")})


@login_required
@require_POST
def account_logout(request):
    logout(request)
    messages.success(request, "You have been signed out.")
    return redirect("shop:home")


@login_required
@require_GET
@never_cache
def account(request):
    orders = request.user.store_orders.prefetch_related("items")
    return render(request, "shop/account.html", {"orders": orders})


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
