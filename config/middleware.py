class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        admin_request = request.path.startswith("/admin/")
        style_policy = "'self' 'unsafe-inline'" if admin_request else "'self'"
        policy = [
            "default-src 'self'",
            "script-src 'self'",
            f"style-src {style_policy}",
            "img-src 'self' https: data:",
            "font-src 'self'",
            "connect-src 'self'",
            "form-action 'self' https://checkout.stripe.com",
            "frame-ancestors 'none'",
            "object-src 'none'",
            "base-uri 'self'",
        ]
        response.setdefault("Content-Security-Policy", "; ".join(policy))
        response.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
        response.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        if admin_request:
            response["Cache-Control"] = "no-store, private"
            response["X-Robots-Tag"] = "noindex, nofollow"
        return response
