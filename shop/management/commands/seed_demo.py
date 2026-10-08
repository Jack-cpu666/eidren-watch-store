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
                "slug": "atelier-01", "name": "Watch 01", "collection": "dress", "price": Decimal("60.00"),
                "short_description": "An ivory dial. A quieter kind of statement.",
                "description": "Clean lines, warm tones, and a considered silhouette. Atelier 01 brings a restrained point of view to the everyday dress watch.\n\nThis is a demonstration listing with concept imagery. Specifications and availability are illustrative; replace this listing with your own verified product information before selling.",
                "image": "images/watch-ivory.png", "image_alt": "Ivory dial dress watch with a polished case and dark leather strap",
                "movement": "Automatic · demo specification", "case_size": "38 mm", "material": "Stainless steel", "water_resistance": "5 ATM · demo specification", "strap": "Leather",
            },
            {
                "slug": "horizon-02", "name": "Watch 02", "collection": "chronograph", "price": Decimal("60.00"),
                "short_description": "Precision in its most compelling form.",
                "description": "A dark dial framed by brushed steel. Horizon 02 balances purposeful detail with a confident, architectural presence.\n\nThis is a demonstration listing with concept imagery. Specifications and availability are illustrative; replace this listing with your own verified product information before selling.",
                "image": "images/watch-noir.png", "image_alt": "Dark dial chronograph watch with brushed stainless steel bracelet",
                "movement": "Quartz chronograph · demo specification", "case_size": "40 mm", "material": "Stainless steel", "water_resistance": "10 ATM · demo specification", "strap": "Stainless steel bracelet",
            },
            {
                "slug": "depth-03", "name": "Watch 03", "collection": "dive", "price": Decimal("60.00"),
                "short_description": "A little further from the ordinary.",
                "description": "Deep green meets brushed steel in a watch designed around a spirit of exploration. An expressive accent for a thoughtfully assembled collection.\n\nThis is a demonstration listing with concept imagery. Specifications and availability are illustrative; replace this listing with your own verified product information before selling.",
                "image": "images/watch-forest.png", "image_alt": "Forest green dial dive watch with stainless steel case and bracelet",
                "movement": "Automatic · demo specification", "case_size": "41 mm", "material": "Stainless steel", "water_resistance": "20 ATM · demo specification", "strap": "Stainless steel bracelet",
            },
        ]
        for values in products:
            slug = values.pop("slug")
            product, created = Product.objects.get_or_create(
                slug=slug,
                defaults={**values, "stock": 12, "is_featured": True, "is_demo": True},
            )
            # Keep the public preview consistent when its intentional sample
            # price or label changes, without touching any real inventory.
            if not created and product.is_demo:
                Product.objects.filter(pk=product.pk).update(name=values["name"], price=values["price"])
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
