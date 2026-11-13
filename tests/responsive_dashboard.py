"""Live responsive workbench: python tests/responsive_dashboard.py  ->  http://127.0.0.1:8765/dash

Serves the app's static files straight from disk (so a CSS edit shows on reload) and forwards API calls to
the fake-WhatsApp preview (python tests/preview_fake.py --port 3003). /dash shows the screen BEFORE and AFTER
responsive.css side by side at any width, plus the fault list from tests/responsive_sweep.js."""

import http.server, socketserver, urllib.request, urllib.error, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACK = "http://127.0.0.1:" + (
    sys.argv[sys.argv.index("--backend") + 1] if "--backend" in sys.argv else "3003"
)
TYPES = {
    ".html": "text/html",
    ".css": "text/css",
    ".js": "text/javascript",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".webmanifest": "application/manifest+json",
}


class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        # "/" is the new design now (the real server builds it); the previous page is /old (index.html)
        name = {"/old": "index.html", "/dash": "tests/responsive_dashboard.html"}.get(
            path, path.lstrip("/")
        )
        if name == "new-ui.css":
            return (
                self.forward()
            )  # the server expands its .UI2 prefix; the raw file matches nothing
        f = (ROOT / name).resolve()
        if ROOT in f.parents and f.is_file() and f.suffix in TYPES and not name.endswith(".py"):
            return self.send(200, f.read_bytes(), TYPES[f.suffix])
        self.forward()

    do_POST = do_PUT = do_DELETE = forward = lambda self: self.proxy()

    def proxy(self):
        n = int(self.headers.get("Content-Length") or 0)
        data = self.rfile.read(n) if n else None
        req = urllib.request.Request(
            BACK + self.path,
            data=data,
            method=self.command,
            headers={
                k: v for k, v in self.headers.items() if k.lower() not in ("host", "content-length")
            },
        )
        try:
            r = urllib.request.urlopen(req, timeout=60)
        except urllib.error.HTTPError as e:
            r = e
        body = r.read()
        self.send_response(r.status if hasattr(r, "status") else r.code)
        for k, v in r.headers.items():
            if k.lower() not in ("transfer-encoding", "connection", "content-length"):
                self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


socketserver.ThreadingTCPServer.allow_reuse_address = True
print("Responsive workbench: http://127.0.0.1:8765/dash", flush=True)
socketserver.ThreadingTCPServer(("127.0.0.1", 8765), H).serve_forever()
