from django.db import migrations


PAGES = {
    "contact": (
        "EIDREN Concierge",
        "For order support, product questions, or return requests, email eidren.concierge.2026@outlook.com. Please include your order number when available.\n\nWe aim to respond within two business days.",
    ),
    "shipping": (
        "Shipping & delivery",
        "Standard shipping is included at no extra cost for addresses accepted at checkout. Orders are processed after payment confirmation and delivered within 14 days. Carrier delays or an incorrect delivery address can affect timing. Tracking details are sent when available.\n\nContact EIDREN Concierge promptly if an order is delayed, arrives damaged, or has an address issue.",
    ),
    "returns": (
        "Returns & aftercare",
        "You may request a return within 30 days of delivery. Email EIDREN Concierge with your order number before sending an item back; we will provide return instructions. Returned items must be unused, unworn, and returned with all supplied packaging and accessories.\n\nAfter inspection, approved refunds are issued to the original payment method. Return-shipping costs are the customer's responsibility unless the item arrived damaged or we sent the wrong item.\n\nEvery EIDREN watch includes a one-year limited warranty from delivery against manufacturing defects. The warranty does not cover normal wear, accidental damage, loss, misuse, unauthorized service, or water damage outside the stated product specification.",
    ),
    "privacy": (
        "Privacy",
        "EIDREN uses essential cookies to keep your bag, account, and checkout secure. We collect the contact, delivery, and order information needed to process purchases, provide support, prevent fraud, and meet record-keeping obligations.\n\nPayments are handled by Stripe. Card details are entered with Stripe and are not stored by this store. Our application is hosted by Render. We do not use advertising or analytics trackers.\n\nYou may contact eidren.concierge.2026@outlook.com to ask about the personal information associated with your order.",
    ),
    "terms": (
        "Terms of sale",
        "These terms apply to purchases from EIDREN. Product prices are shown in US dollars at checkout. Standard shipping is included at no extra cost, and no sales tax is added at checkout.\n\nOrders are subject to product availability and payment confirmation. Product photography and descriptions are provided to help you choose; review each listing before placing an order. Delivery, returns, and warranty coverage are governed by the Shipping & delivery and Returns & aftercare pages.\n\nFor help with an order, email eidren.concierge.2026@outlook.com.",
    ),
}


def publish_pages(apps, schema_editor):
    Page = apps.get_model("shop", "Page")
    for slug, (title, body) in PAGES.items():
        Page.objects.update_or_create(slug=slug, defaults={"title": title, "body": body, "is_published": True})


class Migration(migrations.Migration):
    dependencies = [("shop", "0005_hide_demo_catalog")]

    operations = [migrations.RunPython(publish_pages, migrations.RunPython.noop)]
