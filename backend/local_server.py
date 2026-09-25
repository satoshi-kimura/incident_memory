"""Local development server: serves ../frontend and routes /api/* to the Lambda handler.

  STORE_BACKEND=memory python local_server.py --fixture          # no AWS access at all
  STORE_BACKEND=memory python local_server.py                    # real CloudWatch/CloudTrail via your AWS profile
"""
import argparse
import json
import os
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--fixture", action="store_true", help="use synthetic collectors")
    args = ap.parse_args()

    from app import fixture, handler
    from app.seed_data import sample_memories
    from app.store import get_store
    if args.fixture:
        fixture.install()
    if os.environ.get("STORE_BACKEND") == "memory":
        for m in sample_memories():
            get_store().put(m)

    class H(SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(FRONTEND), **kw)

        def _api(self, method):
            event = {"rawPath": self.path.split("?")[0], "requestContext": {"http": {"method": method}}}
            resp = handler.lambda_handler(event, None)
            self.send_response(resp["statusCode"])
            for k, v in resp["headers"].items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(resp["body"].encode())

        def do_GET(self):
            if self.path.startswith("/api/"):
                return self._api("GET")
            return super().do_GET()

        def do_POST(self):
            if self.path.startswith("/api/"):
                return self._api("POST")
            self.send_error(405)

    print(f"http://localhost:{args.port}", file=sys.stderr)
    ThreadingHTTPServer(("127.0.0.1", args.port), H).serve_forever()


if __name__ == "__main__":
    main()
