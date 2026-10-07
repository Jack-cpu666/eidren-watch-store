"""Enroll a staff account from a trusted interactive server shell."""
import base64
from getpass import getpass

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django_otp.plugins.otp_totp.models import TOTPDevice


class Command(BaseCommand):
    help = "Enroll and verify an administrator's authenticator app. Use a private interactive shell."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("--replace", action="store_true", help="Replace existing TOTP devices only after the new code is verified.")

    def handle(self, *args, **options):
        User = get_user_model()
        try:
            user = User.objects.get(**{User.USERNAME_FIELD: options["username"]})
        except User.DoesNotExist as exc:
            raise CommandError("No such administrator.") from exc
        if not user.is_active or not user.is_staff:
            raise CommandError("The account must be active and have staff access.")
        existing = TOTPDevice.objects.filter(user=user, confirmed=True)
        if existing.exists() and not options["replace"]:
            raise CommandError("This account already has an authenticator. Use --replace only for an authorized recovery.")
        device = TOTPDevice(user=user, name="Authenticator", confirmed=False)
        secret = base64.b32encode(device.bin_key).decode("ascii").rstrip("=")
        self.stdout.write("In your authenticator app, add a time-based account with this secret (keep it private):")
        self.stdout.write(secret)
        self.stdout.write("Issuer: EIDREN Admin. Algorithm: SHA1. Digits: 6. Interval: 30 seconds.")
        try:
            token = getpass("Enter the six-digit code from your app to finish enrollment: ").strip()
        except (EOFError, KeyboardInterrupt) as exc:
            raise CommandError("Enrollment cancelled. Existing devices were preserved.") from exc
        with transaction.atomic():
            device.save()
            if not device.verify_token(token):
                transaction.set_rollback(True)
                raise CommandError("The code was invalid. No authenticator was changed; rerun the command.")
            device.confirmed = True
            device.save(update_fields=["confirmed"])
            if options["replace"]:
                existing.exclude(pk=device.pk).delete()
        self.stdout.write(self.style.SUCCESS("Authenticator verified. Use a fresh code when signing in at /admin/."))
