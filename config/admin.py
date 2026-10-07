from django_otp.admin import OTPAdminSite


class EidrenAdminSite(OTPAdminSite):
    """Every admin route requires a successfully verified OTP device."""

    site_header = "EIDREN · Atelier administration"
    site_title = "EIDREN admin"
    index_title = "Your watch business"

    def __init__(self, name="admin"):
        super().__init__(name=name)
