from django.contrib import admin
from django.core.exceptions import ValidationError
from django import forms

from .models import Order, OrderItem, Page, Product, WebhookEvent


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "collection", "price", "stock", "is_active", "is_featured", "is_demo")
    list_filter = ("is_active", "is_demo", "collection", "is_featured")
    search_fields = ("name", "brand", "slug")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        ("Watch", {"fields": ("name", "slug", "brand", "collection", "price", "short_description", "description")}),
        ("Photography", {"fields": ("image", "image_alt")}),
        ("Specifications", {"fields": ("movement", "case_size", "material", "water_resistance", "strap")}),
        ("Inventory & visibility", {"fields": ("stock", "is_active", "is_featured", "is_demo")}),
        ("Record", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    can_delete = False
    fields = ("product", "product_name", "unit_price", "quantity", "line_total")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


class OrderForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = ("fulfillment", "tracking_number", "tracking_url", "staff_notes")

    def clean(self):
        cleaned = super().clean()
        if "fulfillment" in self.changed_data and self.instance.status != Order.Status.PAID:
            raise ValidationError("Only orders with verified payment can be moved through fulfillment.")
        return cleaned


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    form = OrderForm
    list_display = ("reference", "created_at", "customer_email", "status", "total", "fulfillment")
    list_filter = ("status", "fulfillment", "created_at")
    search_fields = ("id", "customer_email", "customer_name", "stripe_session_id", "stripe_payment_intent", "tracking_number")
    readonly_fields = (
        "id", "status", "created_at", "updated_at", "paid_at", "currency", "subtotal", "shipping_cents", "tax_cents", "total",
        "customer_name", "customer_email", "shipping_address", "stripe_session_id", "stripe_payment_intent", "reserved_until",
    )
    fields = readonly_fields + ("fulfillment", "tracking_number", "tracking_url", "staff_notes")
    inlines = [OrderItemInline]
    date_hierarchy = "created_at"
    actions = None

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Page)
class PageAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "is_published", "updated_at")
    list_filter = ("is_published",)
    prepopulated_fields = {"slug": ("title",)}
    search_fields = ("title", "body")
    readonly_fields = ("updated_at",)


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ("stripe_id", "event_type", "processed_at")
    readonly_fields = ("stripe_id", "event_type", "processed_at")
    search_fields = ("stripe_id",)
    actions = None

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
