"""Shared test helpers: keys removed, sample paths, a tiny local web server."""

import contextlib
import functools
import http.server
import logging
import os
import pathlib
import threading

os.environ.pop("GEMINI_API_KEY", None)
os.environ.pop("OPENAI_API_KEY", None)
logging.disable(logging.INFO)  # keep test output readable

ROOT = pathlib.Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "sample_docs"
PDF = SAMPLES / "patient-guide.pdf"


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@contextlib.contextmanager
def serve_directory(directory):
    """Serve a folder on 127.0.0.1 (random port) for the duration of the block."""
    handler = functools.partial(_Quiet, directory=str(directory))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
