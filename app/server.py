"""HTTP server for the document chatbot (Python standard library only).

Public routes
  GET  /                     sample landing page that embeds the widget
  GET  /widget.js            the embeddable widget (one <script> tag on any site)
  GET  /static/...           CSS / JS / demo pages
  GET  /api/status           business name, sources, current mode
  POST /api/ask              {"question", "session_id"} -> JSON answer with citations
  POST /api/ask/stream       same, streamed as Server-Sent Events (meta / token / replace / done)
  POST /api/lead             {"name", "email", "question"} -> saved to data/leads.jsonl

Admin routes (password via ADMIN_PASSWORD, otherwise only from 127.0.0.1)
  GET  /admin                admin page
  GET  /api/admin/sources    documents and web pages in the index
  POST /api/admin/upload?name=file.pdf   raw file body
  POST /api/admin/url        {"url"}
  POST /api/admin/remove     {"name"}
  POST /api/admin/reindex    {"refetch": true|false}
  GET  /api/admin/unanswered questions the bot could not answer (grouped)
  GET  /api/admin/leads      contact details left in the chat

Run:  python -m app.server
"""

import base64
import hmac
import json
import logging
import mimetypes
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from . import config, llm
from .answerer import answer_events
from .library import Library
from .memory import ConversationMemory
from .ratelimit import RateLimiter
from .store import JsonlLog, unanswered_summary, validate_lead

STATIC_DIR = config.ROOT / "static"
MAX_QUESTION_CHARS = 500
MAX_JSON_BYTES = 10_000

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("pdf-chatbot")


class ChatApp:
    """Everything the request handler needs, so tests can build one on a temp folder."""

    def __init__(self, data_dir=None, seed_dir=None, business=None, contact=None, admin_password=None,
                 rate_limit=None, stream_delay_ms=None, allowed_origins=None, trust_proxy=None):
        data_dir = data_dir or config.DATA_DIR
        self.library = Library(data_dir, seed_dir if seed_dir is not None else config.SEED_DIR)
        self.business = business or config.BUSINESS_NAME
        self.contact = config.BUSINESS_CONTACT if contact is None else contact
        self.admin_password = config.ADMIN_PASSWORD if admin_password is None else admin_password
        self.memory = ConversationMemory()
        self.ask_limiter = RateLimiter(rate_limit or config.RATE_LIMIT_PER_MINUTE, 60)
        self.lead_limiter = RateLimiter(5, 600)
        self.unanswered = JsonlLog(self.library.data_dir / "unanswered.jsonl")
        self.leads = JsonlLog(self.library.data_dir / "leads.jsonl")
        self.stream_delay = (config.STREAM_DELAY_MS if stream_delay_ms is None else stream_delay_ms) / 1000
        self.allowed_origins = allowed_origins or config.ALLOWED_ORIGINS
        self.trust_proxy = config.TRUST_PROXY if trust_proxy is None else trust_proxy

    def events(self, question, session_id):
        """Run the answer pipeline, then update memory and the unanswered log."""
        history = self.memory.history(session_id)
        final = None
        for kind, data in answer_events(question, self.library, self.business, self.contact, history):
            if kind == "done":
                final = data
            yield kind, data
        self.memory.add(session_id, question, final["answer"], topic=final["query"] if final["found"] else "")
        if not final["found"] and not final["guarded"]:
            self.unanswered.append({"question": question})
        log.info("answered found=%s mode=%s guarded=%s", final["found"], final["mode"], final["guarded"])


class ChatHandler(BaseHTTPRequestHandler):
    app: ChatApp = None  # set by make_server
    server_version = "DocChat/2.0"

    # ------------------------------------------------------------ routing

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors_headers()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "600")
        self.end_headers()

    def do_GET(self):
        path = urlsplit(self.path).path
        if path in ("/", "/index.html"):
            return self._send_file(STATIC_DIR / "index.html")
        if path == "/widget.js":
            return self._send_file(STATIC_DIR / "widget.js", cors=True)
        if path.startswith("/static/"):
            target = (STATIC_DIR / path[len("/static/"):]).resolve()
            if STATIC_DIR in target.parents and target.is_file():
                return self._send_file(target)
        if path == "/api/status":
            return self._send_json(self._status(), cors=True)
        if path == "/admin" or path.startswith("/api/admin/"):
            if not self._admin_ok():
                return
            if path == "/admin":
                return self._send_file(STATIC_DIR / "admin.html")
            if path == "/api/admin/sources":
                return self._send_json({"sources": self.app.library.list_sources(), **self._status()})
            if path == "/api/admin/unanswered":
                rows = self.app.unanswered.read(limit=1000)
                return self._send_json({"recent": rows[:50], "grouped": unanswered_summary(rows)})
            if path == "/api/admin/leads":
                return self._send_json({"leads": self.app.leads.read(limit=500)})
        self._send_json({"error": "Not found"}, status=404)

    def do_POST(self):
        parts = urlsplit(self.path)
        path = parts.path
        if path in ("/api/ask", "/api/ask/stream"):
            return self._ask(stream=path.endswith("/stream"))
        if path == "/api/lead":
            return self._lead()
        if path.startswith("/api/admin/"):
            if not self._admin_ok():
                return
            try:
                return self._admin_post(path, parse_qs(parts.query))
            except KeyError:
                return self._send_json({"error": "No such source"}, status=404)
            except ValueError as exc:
                return self._send_json({"error": str(exc)}, status=400)
            except Exception as exc:  # e.g. a URL that cannot be fetched
                log.warning("admin action failed: %s", type(exc).__name__)
                return self._send_json({"error": f"Failed: {type(exc).__name__}"}, status=502)
        self._send_json({"error": "Not found"}, status=404)

    # ------------------------------------------------------------ chat

    def _ask(self, stream):
        allowed, retry = self.app.ask_limiter.allow(self._client_ip())
        if not allowed:
            return self._send_json({"error": "Too many questions - please wait a moment."}, status=429,
                                   cors=True, extra={"Retry-After": str(retry)})
        payload = self._read_json()
        if payload is None:
            return self._send_json({"error": "Invalid JSON"}, status=400, cors=True)
        question = " ".join(str(payload.get("question", "")).split())[:MAX_QUESTION_CHARS]
        if not question:
            return self._send_json({"error": "Please type a question."}, status=400, cors=True)
        session_id = self.app.memory.normalise_id(str(payload.get("session_id", "")))
        events = self.app.events(question, session_id)
        if not stream:
            final = [data for kind, data in events if kind == "done"][-1]  # run to the end
            return self._send_json({**_public(final), "session_id": session_id}, cors=True)

        self.send_response(200)
        self._cors_headers()
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")  # stop nginx from buffering the stream
        self.send_header("Connection", "close")
        self.end_headers()
        offline = not llm.is_available()
        try:
            for kind, data in events:
                if kind == "done":
                    data = {**_public(data), "session_id": session_id}
                self._sse(kind, data)
                if kind == "token" and offline and self.app.stream_delay:
                    time.sleep(self.app.stream_delay)
        except (BrokenPipeError, ConnectionResetError):
            log.info("visitor closed the stream")
        self.close_connection = True

    def _lead(self):
        allowed, retry = self.app.lead_limiter.allow(self._client_ip())
        if not allowed:
            return self._send_json({"error": "Too many requests."}, status=429, cors=True,
                                   extra={"Retry-After": str(retry)})
        payload = self._read_json()
        if payload is None:
            return self._send_json({"error": "Invalid JSON"}, status=400, cors=True)
        if payload.get("website"):  # honeypot field, invisible to people
            return self._send_json({"ok": True}, cors=True)
        try:
            lead = validate_lead(payload)
        except ValueError as exc:
            return self._send_json({"error": str(exc)}, status=400, cors=True)
        self.app.leads.append(lead)
        log.info("lead saved")
        self._send_json({"ok": True, "message": "Thanks! The team will email you soon."}, cors=True)

    # ------------------------------------------------------------ admin

    def _admin_post(self, path, query):
        lib = self.app.library
        if path == "/api/admin/upload":
            name = (query.get("name") or [""])[0]
            length = int(self.headers.get("Content-Length", 0) or 0)
            if length <= 0:
                raise ValueError("Empty upload")
            if length > 15 * 1024 * 1024:
                raise ValueError("File is larger than 15 MB")
            saved = lib.add_file(name, self.rfile.read(length))
            return self._send_json({"ok": True, "name": saved, "chunks": len(lib.chunks)})
        payload = self._read_json() or {}
        if path == "/api/admin/url":
            title = lib.add_url(str(payload.get("url", "")).strip())
            return self._send_json({"ok": True, "title": title, "chunks": len(lib.chunks)})
        if path == "/api/admin/remove":
            lib.remove(str(payload.get("name", "")))
            return self._send_json({"ok": True, "chunks": len(lib.chunks)})
        if path == "/api/admin/reindex":
            count = lib.reindex(refetch=bool(payload.get("refetch")))
            return self._send_json({"ok": True, "chunks": count, "errors": lib.errors})
        raise KeyError(path)

    def _admin_ok(self):
        password = self.app.admin_password
        if password:
            header = self.headers.get("Authorization", "")
            if header.startswith("Basic "):
                try:
                    _, _, given = base64.b64decode(header[6:]).decode("utf-8").partition(":")
                except (ValueError, UnicodeDecodeError):
                    given = ""
                if hmac.compare_digest(given.encode(), password.encode()):
                    return True
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="chatbot admin"')
            self.send_header("Content-Length", "0")
            self.end_headers()
            return False
        if self.client_address[0] in ("127.0.0.1", "::1") and not self.headers.get("X-Forwarded-For"):
            return True
        self._send_json({"error": "Set ADMIN_PASSWORD to use the admin page remotely."}, status=403)
        return False

    # ------------------------------------------------------------ helpers

    def _status(self):
        lib = self.app.library
        return {
            "business": self.app.business,
            "documents": sorted({c.doc for c in lib.chunks}),
            "chunks": len(lib.chunks),
            "mode": llm.provider_name() or "offline",
        }

    def _client_ip(self):
        if self.app.trust_proxy and self.headers.get("X-Forwarded-For"):
            return self.headers["X-Forwarded-For"].split(",")[0].strip()
        return self.client_address[0]

    def _read_json(self):
        try:
            length = int(self.headers.get("Content-Length", 0) or 0)
            if length > MAX_JSON_BYTES:
                return None
            data = json.loads(self.rfile.read(length) or b"{}")
            return data if isinstance(data, dict) else None
        except (ValueError, json.JSONDecodeError):
            return None

    def _cors_headers(self):
        origin = self.headers.get("Origin", "")
        allowed = self.app.allowed_origins
        if "*" in allowed:
            self.send_header("Access-Control-Allow-Origin", "*")
        elif origin in allowed:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")

    def _sse(self, kind, data):
        self.wfile.write(f"event: {kind}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode("utf-8"))
        self.wfile.flush()

    def _send_file(self, path, cors=False):
        body = path.read_bytes()
        self.send_response(200)
        if cors:
            self._cors_headers()
        ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith(("text/", "application/javascript")) else ""))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, data, status=200, cors=False, extra=None):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        if cors:
            self._cors_headers()
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):  # quieter default access log
        log.debug(fmt, *args)


def _public(result):
    """Fields sent to the browser (the internal search query is kept for the logs only)."""
    return {k: v for k, v in result.items() if k != "query"}


def make_server(app, host, port):
    handler = type("BoundChatHandler", (ChatHandler,), {"app": app})
    return ThreadingHTTPServer((host, port), handler)


def main():
    app = ChatApp()
    log.info("Indexed %d chunks from %d sources", len(app.library.chunks), len(app.library.list_sources()))
    log.info("Mode: %s", llm.provider_name() or "offline demo mode (no API key)")
    server = make_server(app, config.HOST, config.PORT)
    log.info("Open http://%s:%d (admin: /admin)", config.HOST, config.PORT)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
