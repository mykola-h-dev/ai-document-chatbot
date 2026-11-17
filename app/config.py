"""Settings loaded from environment variables, with an optional local .env file."""

import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent


def load_dotenv(path=ROOT / ".env"):
    """Load KEY=VALUE lines from the project's .env file (if present) into os.environ.

    Existing environment variables win, so you can override values on the command line.
    """
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_dotenv()

def _path(value):
    path = pathlib.Path(value)
    return path if path.is_absolute() else ROOT / path  # relative paths are relative to the project


DATA_DIR = _path(os.environ.get("DATA_DIR", "data"))              # documents, logs (created on start)
SEED_DIR = _path(os.environ.get("SEED_DIR", "sample_docs"))       # copied into DATA_DIR/docs on first run
BUSINESS_NAME = os.environ.get("BUSINESS_NAME", "Maple Street Dental")
BUSINESS_CONTACT = os.environ.get("BUSINESS_CONTACT", "call 555-0142 or email hello@maplestreetdental.example")
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8000"))

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")             # empty = admin only from this computer
RATE_LIMIT_PER_MINUTE = int(os.environ.get("RATE_LIMIT_PER_MINUTE", "20"))
ALLOWED_ORIGINS = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "*").split(",") if o.strip()]
STREAM_DELAY_MS = int(os.environ.get("STREAM_DELAY_MS", "25"))    # offline mode "typing" speed
TRUST_PROXY = os.environ.get("TRUST_PROXY", "") == "1"            # use X-Forwarded-For behind a proxy
