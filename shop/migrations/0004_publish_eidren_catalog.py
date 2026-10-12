from decimal import Decimal

from django.db import migrations


PRODUCTS = (
    {
        "slug": "aureus-calendar-36", "name": "Aureus Calendar 36", "brand": "EIDREN", "collection": "dress", "price": Decimal("299.99"),
        "short_description": "36 mm gold-tone calendar watch with a champagne dial and three-link bracelet.",
        "description": "Aureus Calendar 36 pairs a warm champagne dial with a fluted gold-tone bezel, day display, magnified date window, and polished three-link bracelet.",
        "image": "images/watch-aureus.png", "image_alt": "Gold-tone 36 mm EIDREN calendar watch with fluted bezel and champagne dial",
        "movement": "Automatic mechanical", "case_size": "36 mm", "material": "Gold-tone stainless steel", "water_resistance": "5 ATM", "strap": "Three-link bracelet",
    },
    {
        "slug": "meridian-gmt-40", "name": "Meridian GMT 40", "brand": "EIDREN", "collection": "dive", "price": Decimal("299.99"),
        "short_description": "40 mm automatic dual-time watch with a red and blue 24-hour bezel and five-link bracelet.",
        "description": "Meridian GMT 40 brings together a high-contrast black dial, luminous markers, a red dual-time hand, and a red and blue 24-hour bezel for a distinctive travel-ready profile.",
        "image": "images/watch-meridian.png", "image_alt": "Stainless steel 40 mm EIDREN dual-time watch with red and blue bezel and five-link bracelet",
        "movement": "Automatic mechanical · dual-time", "case_size": "40 mm", "material": "Stainless steel and ceramic-style bezel", "water_resistance": "10 ATM", "strap": "Five-link stainless steel bracelet",
    },
    {
        "slug": "verdant-pave-40", "name": "Verdant Pavé 40", "brand": "EIDREN", "collection": "chronograph", "price": Decimal("299.99"),
        "short_description": "Full emerald-cut crystal bezel and bracelet with deep green pavé dial and date aperture.",
        "description": "A statement piece set with emerald-tone baguette-cut crystals across the octagonal bezel, integrated case, and link bracelet. A full pavé dial, silver-tone hands, and date window finish the look.",
        "image": "images/watch-emerald.png", "image_alt": "Emerald-tone baguette crystal watch with green pavé dial",
        "movement": "Precision quartz", "case_size": "40 mm", "material": "Stainless steel and emerald-tone crystals", "water_resistance": "3 ATM", "strap": "Integrated crystal-set link bracelet",
    },
)


def publish_catalog(apps, schema_editor):
    Product = apps.get_model("shop", "Product")
    Product.objects.filter(slug__in=("day-date-36-gold", "gmt-master-ii-pepsi", "emerald-baguette-pave")).update(is_active=False)
    for values in PRODUCTS:
        slug = values["slug"]
        defaults = {key: value for key, value in values.items() if key != "slug"}
        defaults.update(stock=25, is_active=True, is_featured=True, is_demo=False)
        Product.objects.update_or_create(slug=slug, defaults=defaults)


def remove_catalog(apps, schema_editor):
    apps.get_model("shop", "Product").objects.filter(slug__in=[product["slug"] for product in PRODUCTS]).delete()


class Migration(migrations.Migration):
    dependencies = [("shop", "0003_order_customer_order_terms_accepted_at_savedcart")]
    operations = [migrations.RunPython(publish_catalog, remove_catalog)]
