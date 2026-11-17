"""Load documents of several kinds and split them into searchable chunks.

Supported sources (all with the Python standard library plus requests/bs4):
  - .pdf   via the `pdftotext` command-line tool (poppler-utils), page by page
  - .txt   plain text; form feeds (\\f) mark page breaks
  - .md    Markdown; `#` headings become section titles
  - .docx  Word files, read straight from the ZIP/XML (no python-docx needed);
           Heading styles become sections, page breaks are counted
  - a web page URL, fetched once; <h1>-<h3> become sections

Every chunk remembers its document, section and page (when the format has pages),
which is what the chatbot uses for its numbered citations.
"""

import re
import subprocess
import zipfile
from dataclasses import dataclass
from xml.etree import ElementTree

import requests
from bs4 import BeautifulSoup

# A numbered heading looks like "4. Services and Prices" on its own line.
HEADING_RE = re.compile(r"^\s*(\d{1,2}\.\s+[A-Z][^\n]{2,60})\s*$")
MD_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$")
MAX_WORDS_PER_CHUNK = 120
SUPPORTED_EXTENSIONS = (".pdf", ".txt", ".md", ".docx")
URL_TIMEOUT = 15
MAX_URL_BYTES = 2_000_000

ACRONYMS = {"faq", "faqs", "pdf", "uk", "eu", "us", "usa", "gdpr", "hr", "it"}
W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


@dataclass
class Chunk:
    text: str
    page: int | None
    section: str
    doc: str = ""

    def citation(self):
        """Human-readable source label, e.g. 'Patient Guide - 4. Services and Prices, page 2'."""
        parts = [p for p in (self.section, f"page {self.page}" if self.page else "") if p]
        where = ", ".join(parts)
        if self.doc and where:
            return f"{self.doc} - {where}"
        return self.doc or where


@dataclass
class Block:
    """A heading or a paragraph of text, with the page it is on."""
    text: str
    page: int | None
    heading: bool = False


# ---------------------------------------------------------------- per-format readers

def extract_pdf_pages(pdf_path):
    """Return a list of page texts (index 0 = page 1)."""
    result = subprocess.run(
        ["pdftotext", "-layout", "-enc", "UTF-8", str(pdf_path), "-"],
        check=True, capture_output=True, timeout=60,
    )
    pages = result.stdout.decode("utf-8", errors="replace").split("\f")
    if pages and not pages[-1].strip():
        pages.pop()
    return pages


def paged_text_blocks(pages):
    """Blocks from page texts, using numbered headings ('2. Opening Hours') as sections."""
    blocks = []
    for page_no, page_text in enumerate(pages, start=1):
        for line in page_text.splitlines():
            match = HEADING_RE.match(line)
            if match:
                blocks.append(Block(match.group(1).strip(), page_no, heading=True))
            elif line.strip():
                blocks.append(Block(line.strip(), page_no))
    return blocks


def markdown_blocks(text):
    blocks = []
    for line in text.splitlines():
        match = MD_HEADING_RE.match(line)
        if match:
            blocks.append(Block(match.group(1).strip(), None, heading=True))
        elif line.strip():
            cleaned = re.sub(r"[*_`>]+", "", line).strip(" -|")
            if cleaned:
                blocks.append(Block(cleaned, None))
    return blocks


def docx_blocks(path):
    """Read paragraphs from word/document.xml. Heading/Title styles become sections."""
    with zipfile.ZipFile(path) as archive:
        xml = archive.read("word/document.xml")
    root = ElementTree.fromstring(xml)
    blocks, page = [], 1
    for para in root.iter(f"{W_NS}p"):
        style = para.find(f"{W_NS}pPr/{W_NS}pStyle")
        style_name = (style.get(f"{W_NS}val") or "") if style is not None else ""
        texts = []
        for node in para.iter():
            if node.tag == f"{W_NS}t" and node.text:
                texts.append(node.text)
            elif node.tag == f"{W_NS}tab":
                texts.append(" ")
            elif node.tag == f"{W_NS}br" and node.get(f"{W_NS}type") == "page":
                page += 1
        text = "".join(texts).strip()
        if text:
            is_heading = style_name.lower().startswith(("heading", "title"))
            blocks.append(Block(text, page, heading=is_heading))
    return blocks


def html_blocks(html):
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "form", "svg"]):
        tag.decompose()
    body = soup.find("main") or soup.find("article") or soup.body or soup
    blocks = []
    for el in body.find_all(["h1", "h2", "h3", "p", "li", "td", "dt", "dd"]):
        text = " ".join(el.get_text(" ", strip=True).split())
        if text:
            blocks.append(Block(text, None, heading=el.name in ("h1", "h2", "h3")))
    return blocks


def page_title(html, fallback):
    soup = BeautifulSoup(html, "lxml")
    title = soup.title.get_text(strip=True) if soup.title else ""
    return title or fallback


def fetch_url(url, session=None):
    """Download one web page (http/https only) and return its HTML text."""
    if not re.match(r"^https?://", url, re.I):
        raise ValueError("Only http:// and https:// URLs are supported")
    http = session or requests
    resp = http.get(url, timeout=URL_TIMEOUT, headers={"User-Agent": "pdf-chatbot-demo/2.0"})
    resp.raise_for_status()
    if "html" not in resp.headers.get("Content-Type", "text/html"):
        raise ValueError("The URL is not an HTML page")
    return resp.text[:MAX_URL_BYTES]


# ---------------------------------------------------------------- chunking

def chunk_blocks(blocks, doc=""):
    """Group blocks into chunks by section and page, capped at MAX_WORDS_PER_CHUNK words."""
    chunks, buffer = [], []
    section, page = "", None

    def flush():
        words = " ".join(buffer).split()
        for start in range(0, len(words), MAX_WORDS_PER_CHUNK):
            chunks.append(Chunk(" ".join(words[start:start + MAX_WORDS_PER_CHUNK]), page, section, doc))
        buffer.clear()

    for block in blocks:
        if block.heading:
            flush()
            section, page = block.text, block.page
            continue
        if block.page != page:
            flush()
            page = block.page
        buffer.append(block.text)
    flush()
    return chunks


def chunk_pages(pages, doc=""):
    """Kept for compatibility: chunk a list of page texts."""
    return chunk_blocks(paged_text_blocks(pages), doc)


def title_from_filename(path):
    stem = re.sub(r"\.[a-z0-9]+$", "", str(path).replace("\\", "/").rsplit("/", 1)[-1], flags=re.I)
    words = re.sub(r"[-_]+", " ", stem).split()
    return " ".join(w.upper() if w.lower() in ACRONYMS else w.capitalize() for w in words)


def load_file(path, title=None):
    """Load a .pdf/.txt/.md/.docx file and return its chunks."""
    path = str(path)
    lower = path.lower()
    title = title or title_from_filename(path)
    if lower.endswith(".pdf"):
        blocks = paged_text_blocks(extract_pdf_pages(path))
    elif lower.endswith(".txt"):
        with open(path, encoding="utf-8", errors="replace") as fh:
            blocks = paged_text_blocks(fh.read().split("\f"))
    elif lower.endswith(".md"):
        with open(path, encoding="utf-8", errors="replace") as fh:
            blocks = markdown_blocks(fh.read())
    elif lower.endswith(".docx"):
        blocks = docx_blocks(path)
    else:
        raise ValueError(f"Unsupported file type: {path}")
    return chunk_blocks(blocks, title)


def load_url_html(url, html):
    """Chunk an already-downloaded web page."""
    return chunk_blocks(html_blocks(html), page_title(html, url))


def load_document(path):
    """Backwards-compatible alias used by older code and tests."""
    return load_file(path)
