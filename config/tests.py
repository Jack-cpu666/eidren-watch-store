from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django_otp.oath import totp
from django_otp.plugins.otp_totp.models import TOTPDevice

from .security import client_ip


class ProxyTrustTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @override_settings(TRUSTED_PROXY_CIDRS=[])
    def test_client_cannot_spoof_forwarded_header(self):
        request = self.factory.get("/", REMOTE_ADDR="203.0.113.11", HTTP_X_FORWARDED_FOR="1.2.3.4")
        self.assertEqual(client_ip(request), "203.0.113.11")

    @override_settings(TRUSTED_PROXY_CIDRS=["10.0.0.0/24"])
    def test_only_verified_proxy_chain_is_followed(self):
        request = self.factory.get("/", REMOTE_ADDR="10.0.0.2", HTTP_X_FORWARDED_FOR="1.2.3.4, 203.0.113.11, 10.0.0.3")
        self.assertEqual(client_ip(request), "203.0.113.11")

    @override_settings(TRUSTED_PROXY_CIDRS=["10.0.0.0/24"])
    def test_malformed_chain_falls_back_to_peer(self):
        request = self.factory.get("/", REMOTE_ADDR="10.0.0.2", HTTP_X_FORWARDED_FOR="203.0.113.11, broken")
        self.assertEqual(client_ip(request), "10.0.0.2")


@override_settings(AXES_ENABLED=True)
class AdminAuthenticationTests(TestCase):
    def setUp(self):
        self.password = "A-test-only-password-68125!"
        self.user = get_user_model().objects.create_superuser("watchkeeper", "keeper@example.com", self.password)
        self.device = TOTPDevice.objects.create(user=self.user, name="Authenticator", confirmed=True)

    def test_password_alone_never_opens_admin(self):
        response = self.client.post(reverse("admin:login"), {"username": self.user.username, "password": self.password})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(self.client.get(reverse("admin:index")).status_code, 302)

    def test_password_and_fresh_totp_open_admin(self):
        token = totp(self.device.bin_key, step=self.device.step, t0=self.device.t0)
        response = self.client.post(reverse("admin:login"), {"username": self.user.username, "password": self.password, "otp_token": str(token).zfill(6), "otp_device": self.device.persistent_id})
        self.assertEqual(response.status_code, 302)
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "no-store, private")
        self.assertIn("frame-ancestors 'none'", response["Content-Security-Policy"])

    def test_password_login_session_without_otp_cannot_bypass_admin(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("admin:index")).status_code, 302)

    def test_bad_passwords_trigger_persistent_lockout(self):
        for _ in range(5):
            response = self.client.post(reverse("admin:login"), {"username": self.user.username, "password": "incorrect"})
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response["Retry-After"], "3600")
        # A forged forwarding header cannot evade the existing username lock.
        response = self.client.post(reverse("admin:login"), {"username": self.user.username, "password": self.password}, HTTP_X_FORWARDED_FOR="1.2.3.4")
        self.assertEqual(response.status_code, 429)

    def test_failed_reenrollment_preserves_existing_device(self):
        original_key = self.device.key
        with patch("config.management.commands.enroll_admin_otp.getpass", return_value="invalid"):
            with self.assertRaises(CommandError):
                call_command("enroll_admin_otp", self.user.username, replace=True, stdout=open_null())
        self.device.refresh_from_db()
        self.assertEqual(self.device.key, original_key)
        self.assertEqual(TOTPDevice.objects.filter(user=self.user).count(), 1)


def open_null():
    from io import StringIO
    return StringIO()
