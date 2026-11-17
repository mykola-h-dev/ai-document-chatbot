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

_doc = pathlib.Path(os.environ.get("DOC_PATH", "sample_docs/maple-street-dental-guide.pdf"))
DOC_PATH = str(_doc if _doc.is_absolute() else ROOT / _doc)  # relative paths are relative to the project
BUSINESS_NAME = os.environ.get("BUSINESS_NAME", "Maple Street Dental")
BUSINESS_CONTACT = os.environ.get("BUSINESS_CONTACT", "call 555-0142 or email hello@maplestreetdental.example")
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8000"))
