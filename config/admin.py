from django.contrib import messages
from django_otp.admin import OTPAdminSite


class EidrenAdminSite(OTPAdminSite):
    """Every admin route requires a successfully verified OTP device."""

    site_header = "EIDREN · Atelier administration"
    site_title = "EIDREN admin"
    index_title = "Your watch business"

    def __init__(self, name="admin"):
        super().__init__(name=name)

    def index(self, request, extra_context=None):
        from shop.readiness import checkout_readiness_issues

        issues = checkout_readiness_issues()
        if issues:
            messages.warning(
                request,
                f"Checkout is closed. {len(issues)} launch items remain: " + " ".join(issues),
            )
        else:
            messages.success(request, "Checkout launch checks are complete.")
        return super().index(request, extra_context=extra_context)
