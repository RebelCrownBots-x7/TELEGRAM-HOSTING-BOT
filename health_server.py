"""
Minimal HTTP health server for cloud platforms (Railway, Render, Fly, etc.)
that require the process to bind to $PORT. Uses only the Python standard library.
"""

import os
import threading
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer

logger = logging.getLogger("health_server")

_started = False


class _HealthHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Keep access logs quiet unless debugging
        logger.debug("%s - %s", self.address_string(), format % args)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/health", "/healthz", "/ready", "/ping"):
            body = b'{"status":"ok","service":"rebel-crown-hosting"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            body = b'{"error":"not found"}'
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def do_HEAD(self):
        path = self.path.split("?", 1)[0]
        code = 200 if path in ("/", "/health", "/healthz", "/ready", "/ping") else 404
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()


def start_health_server(port: int = None):
    """
    Start a background HTTP server on PORT (env) or the given port.
    Returns the bound port, or None if disabled / failed.
    Set HEALTH_SERVER=0 to disable.
    """
    global _started
    if _started:
        return None
    if os.getenv("HEALTH_SERVER", "1").strip() in ("0", "false", "no"):
        logger.info("Health server disabled by HEALTH_SERVER env")
        return None

    if port is None:
        raw = os.getenv("PORT", "").strip()
        if not raw:
            # No PORT set (typical local / Termux) — skip unless forced
            if os.getenv("FORCE_HEALTH_SERVER", "").strip() not in ("1", "true", "yes"):
                return None
            port = int(os.getenv("HEALTH_PORT", "8080"))
        else:
            try:
                port = int(raw)
            except ValueError:
                logger.warning("Invalid PORT=%r — health server skipped", raw)
                return None

    try:
        server = HTTPServer(("0.0.0.0", port), _HealthHandler)
        t = threading.Thread(target=server.serve_forever, name="health-http", daemon=True)
        t.start()
        _started = True
        logger.info("Health server listening on 0.0.0.0:%s", port)
        print(f"✅ Health server on http://0.0.0.0:{port}/health")
        return port
    except OSError as e:
        logger.warning("Could not bind health server on port %s: %s", port, e)
        print(f"⚠️ Health server failed to bind port {port}: {e}")
        return None
