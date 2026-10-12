from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from shop.models import Page, Product


class Command(BaseCommand):
    help = "Add clearly marked demonstration watches and editable draft-policy examples without overwriting existing records."

    def handle(self, *args, **options):
        if not (settings.DEBUG or settings.DEMO_MODE):
            raise CommandError("Demo content is disabled. Use this command only in a preview environment.")
        products = [
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
                "image": "images/watch-emerald.png", "image_alt": "Luxury emerald green baguette crystal iced out watch with green pave dial",
                "movement": "Precision quartz", "case_size": "40 mm", "material": "Stainless steel and emerald-tone crystals", "water_resistance": "3 ATM", "strap": "Integrated crystal-set link bracelet",
            },
        ]
        for values in products:
            slug = values.pop("slug")
            product, created = Product.objects.get_or_create(
                slug=slug,
                defaults={**values, "stock": 25, "is_featured": True, "is_demo": False},
            )
            if not created:
                Product.objects.filter(pk=product.pk).update(**values, is_demo=False)
        pages = {
            "about": ("A considered approach to time", "EIDREN is a watch-store concept built around considered design and the everyday ritual of wearing a watch.\n\nThis storefront is a demonstration. The store owner can replace this page with the real business story, product sourcing, and service commitments in the admin panel."),
            "contact": ("A conversation starts here", f"For questions about this store, contact {settings.STORE_EMAIL}.\n\nStore owner: replace this draft with your verified business name, contact information, location, and support hours before accepting orders."),
            "shipping": ("Shipping & delivery", "Draft policy — store owner review required.\n\nShipping destinations and the shipping charge appear at checkout. Before launch, publish your actual dispatch times, carrier details, delivery estimates, duties and import-tax responsibilities, and process for lost or damaged shipments. No delivery time is promised by this demonstration storefront."),
            "returns": ("Returns & aftercare", "Draft policy — store owner review required.\n\nBefore accepting orders, publish your actual return window, eligibility requirements, return-address process, shipping-cost responsibilities, refund timing, warranty coverage, and any applicable exceptions. Contact the store before sending an item back."),
            "privacy": ("Privacy", "Draft privacy notice — store owner review required.\n\nThis store uses essential session and security cookies to keep your bag and checkout working. Checkout is hosted by Stripe; card details are entered on Stripe and are not stored by this application. The store receives order, contact, and delivery information needed to process purchases.\n\nBefore launch, identify your business and contact, legal basis for processing where applicable, hosting and payment providers, retention periods, international transfers, individual rights, and applicable privacy disclosures. No marketing or analytics tracker is included in this starter."),
            "terms": ("Terms of sale", "Draft terms — store owner review required.\n\nBefore accepting payments, publish your business identity, currency and tax information, order-acceptance terms, product accuracy standards, payment conditions, delivery and returns terms, warranty details, and applicable consumer rights. Demonstration watches, illustrations, prices, and specifications are examples and must be replaced before selling."),
        }
        for slug, (title, body) in pages.items():
            Page.objects.get_or_create(slug=slug, defaults={"title": title, "body": body, "is_published": True})
        self.stdout.write(self.style.SUCCESS("Demo watches and clearly labeled policy drafts are ready. Existing content was preserved."))
