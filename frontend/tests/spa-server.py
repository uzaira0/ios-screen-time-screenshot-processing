"""SPA-aware static file server. Falls back to index.html for non-file routes."""

import http.server
import os
import socketserver
import sys

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 9091
DIRECTORY = sys.argv[2] if len(sys.argv) > 2 else "dist"


class SPAHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def do_GET(self):
        # Try serving the actual file first
        file_path = os.path.join(DIRECTORY, self.path.lstrip("/"))
        if os.path.isfile(file_path):
            return super().do_GET()

        # For SPA routes (no file extension), serve index.html
        if "." not in os.path.basename(self.path):
            self.path = "/index.html"

        return super().do_GET()


socketserver.TCPServer.allow_reuse_address = True
with socketserver.TCPServer(("127.0.0.1", PORT), SPAHandler) as httpd:
    print(f"SPA server on http://127.0.0.1:{PORT} serving {DIRECTORY}")
    httpd.serve_forever()
