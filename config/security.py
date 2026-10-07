"""Resolve client addresses only through explicitly trusted proxy networks."""
from ipaddress import ip_address, ip_network

from django.conf import settings
from django.http import HttpResponse


def client_ip(request):
    try:
        remote = ip_address(request.META.get("REMOTE_ADDR", ""))
    except ValueError:
        return None
    networks = [ip_network(value, strict=False) for value in settings.TRUSTED_PROXY_CIDRS]

    def trusted(address):
        return any(address in network for network in networks)

    if not trusted(remote):
        return str(remote)
    # Walk from the trusted peer towards the client. Never trust an arbitrary
    # left-most address supplied by a visitor.
    chain = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")
    for value in reversed(chain):
        try:
            address = ip_address(value.strip())
        except ValueError:
            return str(remote)
        if not trusted(address):
            return str(address)
    return str(remote)


def lockout_response(request, response=None, credentials=None, *args, **kwargs):
    result = HttpResponse(
        "Too many sign-in attempts. Please wait one hour before trying again, or contact the store administrator.",
        status=429,
        content_type="text/plain; charset=utf-8",
    )
    result["Retry-After"] = "3600"
    return result
