"""Bound concurrent HTTP handlers instead of creating unlimited worker threads.

Overload is rejected before a handler or a send can run; it is never replayed here.
This protects process memory, not a promise of mass concurrency on free compute.
"""

from http.server import ThreadingHTTPServer
import threading
import ops


class BoundedHTTPServer(ThreadingHTTPServer):
    request_queue_size = 1024
    daemon_threads = True

    def __init__(self, address, handler, max_workers=32):
        if not 1 <= max_workers <= 256:
            raise ValueError("HTTP_MAX_WORKERS must be between 1 and 256.")
        self._slots = threading.BoundedSemaphore(max_workers)
        super().__init__(address, handler)

    def process_request(self, request, client_address):
        if not self._slots.acquire(blocking=False):
            body = b'{"error":"Server is busy. Try again shortly.","code":"OVERLOADED"}'
            headers = {
                "Content-Type": "application/json",
                "Content-Length": str(len(body)),
                "Retry-After": "5",
                "Connection": "close",
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                **ops.security_headers(),
            }
            wire = (
                "HTTP/1.1 503 Service Unavailable\r\n"
                + "".join(k + ": " + v + "\r\n" for k, v in headers.items())
                + "\r\n"
            ).encode() + body
            try:
                request.settimeout(1)
                request.sendall(wire)
            except OSError:
                pass
            finally:
                self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()
