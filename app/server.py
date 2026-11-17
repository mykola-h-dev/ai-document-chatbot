"""HTTP server for the PDF chatbot demo (Python standard library only).

Routes:
  GET  /            -> sample landing page with the chat widget
  GET  /static/...  -> CSS / JS
  GET  /api/status  -> document info and current mode (ai / offline)
  POST /api/ask     -> {"question": "..."} -> {"answer", "sources", "mode", "found"}

Run:  python -m app.server
"""

import json
import logging
import mimetypes
from urllib.parse import urlsplit
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import config, llm
from .answerer import answer
from .pdf_loader import load_document
from .retriever import BM25Index

STATIC_DIR = config.ROOT / "static"
MAX_QUESTION_CHARS = 500

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("pdf-chatbot")


def build_index():
    chunks = load_document(config.DOC_PATH)
    log.info("Loaded %d chunks from %s", len(chunks), config.DOC_PATH)
    return BM25Index(chunks)


INDEX = None  # created in main() so importing this module stays cheap


class ChatHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlsplit(self.path).path  # ignore ?query strings such as ?autoplay
        if path in ("/", "/index.html"):
            return self._send_file(STATIC_DIR / "index.html")
        if path.startswith("/static/"):
            target = (STATIC_DIR / path[len("/static/"):]).resolve()
            if STATIC_DIR in target.parents and target.is_file():
                return self._send_file(target)
        if path == "/api/status":
            return self._send_json({
                "business": config.BUSINESS_NAME,
                "document": config.DOC_PATH.rsplit("/", 1)[-1],
                "chunks": len(INDEX.chunks),
                "mode": llm.provider_name() or "offline",
            })
        self._send_json({"error": "Not found"}, status=404)

    def do_POST(self):
        if self.path != "/api/ask":
            return self._send_json({"error": "Not found"}, status=404)
        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(min(length, 10_000)) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return self._send_json({"error": "Invalid JSON"}, status=400)
        question = str(payload.get("question", "")).strip()[:MAX_QUESTION_CHARS]
        if not question:
            return self._send_json({"error": "Please type a question."}, status=400)
        result = answer(question, INDEX, config.BUSINESS_NAME, config.BUSINESS_CONTACT)
        log.info("Q=%r found=%s mode=%s", question, result["found"], result["mode"])
        self._send_json(result)

    def _send_file(self, path):
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(str(path))[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, data, status=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):  # quieter default access log
        log.debug(fmt, *args)


def main():
    global INDEX
    INDEX = build_index()
    mode = llm.provider_name() or "offline demo mode (no API key)"
    log.info("Mode: %s", mode)
    server = ThreadingHTTPServer((config.HOST, config.PORT), ChatHandler)
    log.info("Open http://%s:%d in your browser", config.HOST, config.PORT)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
