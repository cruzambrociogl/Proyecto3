"""Web server for the chat room: static page, JSON API, live LOG over Server-Sent Events."""
import json
import os
import queue
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

STATIC = os.path.join(os.path.dirname(__file__), "static")


def serve(node, port, host="0.0.0.0"):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _json(self, obj, code=200):
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _body(self):
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n) or b"{}")

        def do_GET(self):
            path = self.path.split("?")[0]
            if path in ("/", "/index.html"):
                with open(os.path.join(STATIC, "index.html"), "rb") as f:
                    body = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif path == "/state":
                self._json(node.state())
            elif path == "/events":
                self._events(once="once=1" in self.path)
            else:
                self._json({"error": "not found"}, 404)

        def do_POST(self):
            try:
                body = self._body()
                if self.path == "/send":
                    text = body.get("text", "")
                    if not text:
                        return self._json({"error": "empty"}, 400)
                    return self._json({"id": node.send(text)})
                if self.path == "/config":
                    node.configure(crc=body.get("crc"), encoding=body.get("encoding"),
                                   noise_p=body.get("noise_p"), scope=body.get("scope"))
                    return self._json(node.state())
                if self.path == "/interfere":
                    if not hasattr(node.phy, "interfere"):
                        return self._json({"error": "solo en PHY simulado; interfiera el medio real"}, 400)
                    ticks = body.get("ticks")
                    node.interfere(body["channel"], body.get("mode", "off"), int(ticks) if ticks else None)
                    return self._json(node.state())
                self._json({"error": "not found"}, 404)
            except (ValueError, KeyError) as e:
                self._json({"error": str(e)}, 400)

        def _events(self, once=False):
            """Live LOG stream; once=True sends the backlog and closes (static snapshots)."""
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            q, backlog = node.bus.subscribe()
            try:
                for ev in backlog:
                    self._sse(ev)
                while not once:
                    try:
                        self._sse(q.get(timeout=15))
                    except queue.Empty:
                        self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                node.bus.unsubscribe(q)

        def _sse(self, ev):
            self.wfile.write(b"data: " + json.dumps(ev, ensure_ascii=False).encode("utf-8") + b"\n\n")
            self.wfile.flush()

    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    server.serve_forever()
