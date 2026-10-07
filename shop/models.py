import uuid
from decimal import Decimal
from urllib.parse import urlparse

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.templatetags.static import static
from django.urls import reverse


class Product(models.Model):
    class Collection(models.TextChoices):
        DRESS = "dress", "Dress watches"
        DIVE = "dive", "Dive watches"
        CHRONOGRAPH = "chronograph", "Chronographs"

    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=180, unique=True)
    brand = models.CharField(max_length=80, default="EIDREN")
    collection = models.CharField(max_length=20, choices=Collection.choices)
    price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.50"))])
    short_description = models.CharField(max_length=240)
    description = models.TextField()
    image = models.CharField(max_length=1000, default="images/watch-noir.png", help_text="HTTPS image URL from your image host, or a bundled path such as images/watch-noir.png. Render does not retain local uploads.")
    image_alt = models.CharField(max_length=220, blank=True)
    movement = models.CharField(max_length=140, blank=True)
    case_size = models.CharField(max_length=80, blank=True)
    material = models.CharField(max_length=140, blank=True)
    water_resistance = models.CharField(max_length=100, blank=True)
    strap = models.CharField(max_length=140, blank=True)
    stock = models.PositiveIntegerField(default=0, help_text="Available units. Open checkouts reserve stock immediately; expired checkouts restore it. Do not include reserved units here.")
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    is_demo = models.BooleanField(default=False, help_text="Sample product. Never accepted with live Stripe keys.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_featured", "name"]
        constraints = [models.CheckConstraint(condition=models.Q(price__gte=Decimal("0.50")), name="product_price_positive")]
        indexes = [models.Index(fields=["is_active", "collection"])]

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if self.image.startswith("https://"):
            if not urlparse(self.image).hostname:
                raise ValidationError({"image": "Enter a valid HTTPS image URL."})
        elif ":" in self.image or self.image.startswith(("/", "\\")) or ".." in self.image or "\\" in self.image:
            raise ValidationError({"image": "Use an HTTPS URL or a relative bundled image path."})

    @property
    def image_url(self):
        return self.image if self.image.startswith("https://") else static(self.image)

    @property
    def price_cents(self):
        return int(self.price * 100)

    @property
    def purchase_limit(self):
        return min(self.stock, 10)

    def get_absolute_url(self):
        return reverse("shop:product_detail", args=[self.slug])


class Page(models.Model):
    slug = models.SlugField(unique=True)
    title = models.CharField(max_length=180)
    body = models.TextField(help_text="Plain text only; paragraphs are preserved. Publish accurate store policies before going live.")
    is_published = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["title"]

    def __str__(self):
        return self.title


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Awaiting payment"
        PAID = "paid", "Paid"
        EXPIRED = "expired", "Expired / canceled"
        REVIEW = "review", "Payment requires review"
        REFUNDED = "refunded", "Fully refunded"

    class Fulfillment(models.TextChoices):
        UNFULFILLED = "unfulfilled", "Unfulfilled"
        PACKING = "packing", "Packing"
        SHIPPED = "shipped", "Shipped"
        DELIVERED = "delivered", "Delivered"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    browser_key = models.UUIDField(db_index=True, editable=False)
    cart_fingerprint = models.CharField(max_length=64, editable=False)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    fulfillment = models.CharField(max_length=20, choices=Fulfillment.choices, default=Fulfillment.UNFULFILLED)
    tracking_number = models.CharField(max_length=200, blank=True)
    tracking_url = models.URLField(max_length=1000, blank=True)
    staff_notes = models.TextField(blank=True)
    currency = models.CharField(max_length=3, default="usd", editable=False)
    subtotal_cents = models.PositiveIntegerField(editable=False)
    shipping_cents = models.PositiveIntegerField(default=0, editable=False)
    tax_cents = models.PositiveIntegerField(default=0, editable=False)
    total_cents = models.PositiveIntegerField(default=0, editable=False)
    stripe_session_id = models.CharField(max_length=255, blank=True, default="", db_index=True, editable=False)
    stripe_payment_intent = models.CharField(max_length=255, blank=True, db_index=True, editable=False)
    stripe_checkout_url = models.URLField(max_length=2000, blank=True, editable=False)
    checkout_payload = models.JSONField(default=dict, editable=False)
    customer_email = models.EmailField(blank=True, editable=False)
    customer_name = models.CharField(max_length=240, blank=True, editable=False)
    shipping_address = models.JSONField(default=dict, blank=True, editable=False)
    reserved_until = models.DateTimeField(editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    paid_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["stripe_session_id"], condition=~models.Q(stripe_session_id=""), name="unique_stripe_checkout")]

    def __str__(self):
        return f"{self.reference} · {self.get_status_display()}"

    @property
    def reference(self):
        return str(self.id).split("-")[0].upper()

    @property
    def subtotal(self):
        return Decimal(self.subtotal_cents) / 100

    @property
    def total(self):
        return Decimal(self.total_cents) / 100

    def clean(self):
        super().clean()
        if self.fulfillment != self.Fulfillment.UNFULFILLED and self.status != self.Status.PAID:
            raise ValidationError({"fulfillment": "Only a confirmed paid order can be fulfilled."})
        if self.tracking_url and not self.tracking_url.startswith("https://"):
            raise ValidationError({"tracking_url": "Tracking links must use HTTPS."})


class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    product_name = models.CharField(max_length=160)
    unit_price_cents = models.PositiveIntegerField()
    quantity = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(quantity__gte=1), name="order_item_quantity_positive")]

    @property
    def unit_price(self):
        return Decimal(self.unit_price_cents) / 100

    @property
    def line_total(self):
        return self.unit_price * self.quantity

    def __str__(self):
        return f"{self.quantity} × {self.product_name}"


class CheckoutState(models.Model):
    """One locked row per visitor prevents overlapping inventory reservations."""
    browser_key = models.UUIDField(primary_key=True)
    current_order = models.ForeignKey(Order, null=True, blank=True, on_delete=models.SET_NULL)
    updated_at = models.DateTimeField(auto_now=True)


class WebhookEvent(models.Model):
    stripe_id = models.CharField(max_length=255, primary_key=True)
    event_type = models.CharField(max_length=100)
    processed_at = models.DateTimeField(auto_now_add=True)


class RateLimitBucket(models.Model):
    key = models.CharField(max_length=64, primary_key=True)
    window_started = models.DateTimeField()
    count = models.PositiveIntegerField(default=0)
