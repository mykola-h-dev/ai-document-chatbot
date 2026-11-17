"""The chatbot's knowledge base: a folder of files plus a list of web pages.

  data/docs/            uploaded or sample files (.pdf .txt .md .docx)
  data/sources.json     web pages added by URL, with their downloaded text cached

The library builds one BM25 index over everything and can add, remove and
re-index sources while the server is running (used by the admin page).
"""

import json
import pathlib
import re
import shutil
import threading
import time

from .loaders import SUPPORTED_EXTENSIONS, Chunk, fetch_url, load_file, load_url_html, title_from_filename
from .retriever import BM25Index

SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._ -]+")
MAX_UPLOAD_BYTES = 15 * 1024 * 1024


def safe_filename(name):
    """Strip directories and odd characters from an uploaded file name."""
    name = SAFE_NAME_RE.sub("", str(name).replace("\\", "/").rsplit("/", 1)[-1]).strip(" .")
    if not name or not name.lower().endswith(SUPPORTED_EXTENSIONS):
        raise ValueError(f"Allowed file types: {', '.join(SUPPORTED_EXTENSIONS)}")
    return name


class Library:
    def __init__(self, data_dir, seed_dir=None, fetch=fetch_url):
        self.data_dir = pathlib.Path(data_dir)
        self.docs_dir = self.data_dir / "docs"
        self.sources_path = self.data_dir / "sources.json"
        self._fetch = fetch
        self._lock = threading.RLock()
        self.docs_dir.mkdir(parents=True, exist_ok=True)
        marker = self.data_dir / ".seeded"
        if seed_dir and not marker.exists():  # first start: copy the sample documents once
            for path in sorted(pathlib.Path(seed_dir).iterdir()):
                if path.suffix.lower() in SUPPORTED_EXTENSIONS and not (self.docs_dir / path.name).exists():
                    shutil.copy2(path, self.docs_dir / path.name)
            marker.write_text("sample documents copied\n", encoding="utf-8")
        self.errors = {}
        self.index = BM25Index([])
        self.reindex(refetch=False)

    # ------------------------------------------------------------ sources

    def _load_urls(self):
        if not self.sources_path.exists():
            return []
        return json.loads(self.sources_path.read_text(encoding="utf-8")).get("urls", [])

    def _save_urls(self, urls):
        self.sources_path.write_text(json.dumps({"urls": urls}, indent=2), encoding="utf-8")

    def files(self):
        return sorted(p for p in self.docs_dir.iterdir() if p.suffix.lower() in SUPPORTED_EXTENSIONS)

    def list_sources(self):
        """What the admin page shows: every file and URL with its chunk count."""
        with self._lock:
            counts = {}
            for chunk in self.index.chunks:
                counts[chunk.doc] = counts.get(chunk.doc, 0) + 1
            items = []
            for path, title in self._file_titles():
                items.append({"kind": "file", "name": path.name, "title": title,
                              "size": path.stat().st_size, "chunks": counts.get(title, 0),
                              "error": self.errors.get(path.name)})
            for entry in self._load_urls():
                items.append({"kind": "url", "name": entry["url"], "title": entry.get("title", entry["url"]),
                              "fetched_at": entry.get("fetched_at"), "chunks": counts.get(entry.get("title"), 0),
                              "error": self.errors.get(entry["url"])})
            return items

    def _file_titles(self):
        return [(path, title_from_filename(path)) for path in self.files()]

    # ------------------------------------------------------------ changes

    def add_file(self, filename, data):
        if len(data) > MAX_UPLOAD_BYTES:
            raise ValueError("File is larger than 15 MB")
        name = safe_filename(filename)
        with self._lock:
            target = self.docs_dir / name
            target.write_bytes(data)
            try:
                load_file(target)  # validate before indexing; bad files are not kept
            except Exception as exc:
                target.unlink(missing_ok=True)
                raise ValueError(f"Could not read {name}: {type(exc).__name__}") from exc
            self.reindex(refetch=False)
            return name

    def add_url(self, url):
        with self._lock:
            html = self._fetch(url)
            chunks = load_url_html(url, html)
            if not chunks:
                raise ValueError("No readable text found on that page")
            urls = [u for u in self._load_urls() if u["url"] != url]
            urls.append({"url": url, "title": chunks[0].doc, "html": html, "fetched_at": int(time.time())})
            self._save_urls(urls)
            self.reindex(refetch=False)
            return chunks[0].doc

    def remove(self, name):
        with self._lock:
            urls = self._load_urls()
            remaining = [u for u in urls if u["url"] != name]
            if len(remaining) != len(urls):
                self._save_urls(remaining)
            else:
                path = self.docs_dir / safe_filename(name)
                if not path.exists():
                    raise KeyError(name)
                path.unlink()
            self.errors.pop(name, None)
            self.reindex(refetch=False)

    def reindex(self, refetch=False):
        """Rebuild the search index from all sources. refetch=True downloads URLs again."""
        with self._lock:
            chunks, errors = [], {}
            for path in self.files():
                try:
                    chunks.extend(load_file(path))
                except Exception as exc:  # one broken file must not take the bot down
                    errors[path.name] = f"{type(exc).__name__}: {exc}"[:200]
            urls = self._load_urls()
            for entry in urls:
                try:
                    if refetch:
                        entry["html"] = self._fetch(entry["url"])
                        entry["fetched_at"] = int(time.time())
                    url_chunks = load_url_html(entry["url"], entry.get("html", ""))
                    entry["title"] = url_chunks[0].doc if url_chunks else entry["url"]
                    chunks.extend(url_chunks)
                except Exception as exc:
                    errors[entry["url"]] = f"{type(exc).__name__}: {exc}"[:200]
                    chunks.extend(load_url_html(entry["url"], entry.get("html", "")))  # keep old copy
            if refetch:
                self._save_urls(urls)
            self.errors = errors
            self.index = BM25Index(chunks)
            return len(chunks)

    def search(self, query, top_k=4):
        with self._lock:
            index = self.index
        return index.search(query, top_k=top_k)

    @property
    def chunks(self) -> list[Chunk]:
        return self.index.chunks

    @property
    def idf(self):
        return self.index.idf
