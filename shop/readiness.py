"""Launch checks that keep checkout closed until store policies are real."""

from django.conf import settings

from .models import Page, Product


REQUIRED_POLICY_SLUGS = ("contact", "shipping", "returns", "privacy", "terms")
DRAFT_MARKERS = (
    "draft policy",
    "draft privacy",
    "draft terms",
    "store owner:",
    "before launch",
    "before accepting",
    "demonstration storefront",
)


def checkout_readiness_issues():
    """Return private launch issues without exposing business details to shoppers."""
    issues = []
    email = settings.STORE_EMAIL.strip().lower()
    if not email or email.endswith("@example.com"):
        issues.append("Set a monitored customer-service email address.")

    if not Product.objects.filter(is_active=True, is_demo=False, stock__gt=0).exists():
        issues.append("Publish at least one verified, in-stock product listing.")

    pages = {
        page.slug: page
        for page in Page.objects.filter(slug__in=REQUIRED_POLICY_SLUGS)
    }
    for slug in REQUIRED_POLICY_SLUGS:
        page = pages.get(slug)
        if page is None or not page.is_published or not page.body.strip():
            issues.append(f"Publish the {slug} page.")
            continue
        body = page.body.casefold()
        if any(marker in body for marker in DRAFT_MARKERS):
            issues.append(f"Replace the draft {slug} page.")
    return tuple(issues)


def checkout_is_ready():
    return not checkout_readiness_issues()
