"""Extract text from a PDF page by page and split it into searchable chunks.

Uses the `pdftotext` command-line tool (part of poppler-utils), so no Python
PDF library is needed. Each chunk remembers its page number and section title,
which lets the chatbot cite where an answer came from.
"""

import re
import subprocess
from dataclasses import dataclass

# A heading looks like "4. Services and Prices" on its own line.
HEADING_RE = re.compile(r"^\s*(\d{1,2}\.\s+[A-Z][^\n]{2,60})\s*$")
MAX_WORDS_PER_CHUNK = 120


@dataclass
class Chunk:
    text: str
    page: int
    section: str

    def citation(self):
        return f"{self.section}, page {self.page}" if self.section else f"page {self.page}"


def extract_pages(pdf_path):
    """Return a list of page texts (index 0 = page 1)."""
    result = subprocess.run(
        ["pdftotext", "-layout", "-enc", "UTF-8", str(pdf_path), "-"],
        check=True, capture_output=True, timeout=60,
    )
    text = result.stdout.decode("utf-8", errors="replace")
    pages = text.split("\f")  # pdftotext separates pages with form feeds
    if pages and not pages[-1].strip():
        pages.pop()
    return pages


def load_text_file(txt_path):
    """Treat a plain-text file as a document; form feeds (\\f) mark page breaks."""
    with open(txt_path, encoding="utf-8") as fh:
        return fh.read().split("\f")


def chunk_pages(pages):
    """Split pages into chunks by section heading, then by size."""
    chunks = []
    section = ""
    for page_no, page_text in enumerate(pages, start=1):
        buffer = []
        for line in page_text.splitlines():
            match = HEADING_RE.match(line)
            if match:
                _flush(buffer, page_no, section, chunks)
                buffer = []
                section = match.group(1).strip()
                continue
            if line.strip():
                buffer.append(line.strip())
        _flush(buffer, page_no, section, chunks)
    return chunks


def _flush(lines, page_no, section, chunks):
    """Turn collected lines into one or more chunks of limited size."""
    words = " ".join(lines).split()
    for start in range(0, len(words), MAX_WORDS_PER_CHUNK):
        piece = " ".join(words[start:start + MAX_WORDS_PER_CHUNK])
        if piece:
            chunks.append(Chunk(text=piece, page=page_no, section=section))


def load_document(path):
    """Load a .pdf or .txt document and return its chunks."""
    path = str(path)
    pages = load_text_file(path) if path.lower().endswith(".txt") else extract_pages(path)
    return chunk_pages(pages)
