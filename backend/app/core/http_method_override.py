"""HTTP method override for gateways that reset PUT/PATCH/DELETE connections.

The public entry of the Guangdong deployment (firewall NAT 8093 -> 8092)
resets TCP connections whose request line is ``PUT``/``PATCH``/``DELETE``,
while ``GET``/``POST`` pass. The frontend therefore sends such mutations as
``POST`` with an ``X-HTTP-Method-Override`` header; this middleware restores
the real method on the ASGI scope before routing. Direct PUT/DELETE/PATCH
requests (intranet clients) carry no header and pass through untouched.
"""

import structlog

OVERRIDE_HEADER = "x-http-method-override"
OVERRIDABLE_METHODS = ("PUT", "DELETE", "PATCH")

logger = structlog.get_logger()


class HttpMethodOverrideMiddleware:
    """Rewrite POST requests carrying ``X-HTTP-Method-Override`` to the real method."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("method") == "POST":
            header_name = OVERRIDE_HEADER.encode("latin-1")
            for name, value in scope.get("headers") or []:
                if name == header_name:
                    override = value.decode("latin-1").strip().upper()
                    if override in OVERRIDABLE_METHODS:
                        scope["method"] = override
                        logger.info(
                            "http_method_overridden",
                            override=override,
                            path=scope.get("path"),
                        )
                    break
        await self.app(scope, receive, send)
