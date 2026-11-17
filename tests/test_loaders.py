import pathlib
import sys
import tempfile
import unittest

from tests.helpers import ROOT, serve_directory
from app.library import safe_filename
from app.loaders import chunk_blocks, docx_blocks, fetch_url, html_blocks, load_file, load_url_html, markdown_blocks

sys.path.insert(0, str(ROOT / "scripts"))
from make_sample_docs import build_docx  # noqa: E402


class DocxTests(unittest.TestCase):
    def test_headings_and_page_breaks(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "policy.docx"
            build_docx(path, [("Heading1", "Returns"), (None, "Returns accepted within 30 days."),
                              "PAGE_BREAK", ("Heading1", "Delivery"), (None, "Free delivery over $50 & up.")])
            chunks = load_file(path)
        self.assertEqual([(c.section, c.page) for c in chunks], [("Returns", 1), ("Delivery", 2)])
        self.assertEqual(chunks[1].text, "Free delivery over $50 & up.")  # XML entities decoded
        self.assertEqual(chunks[0].doc, "Policy")
        self.assertEqual(chunks[0].citation(), "Policy - Returns, page 1")

    def test_sample_docx(self):
        blocks = docx_blocks(ROOT / "sample_docs" / "aftercare-sheet.docx")
        self.assertTrue(any(b.heading and b.text == "After Teeth Whitening" and b.page == 2 for b in blocks))


class TextFormatTests(unittest.TestCase):
    def test_markdown_sections(self):
        chunks = chunk_blocks(markdown_blocks("# Shop FAQ\n\n## Delivery\n\n- **Free** over $50\n\n## Returns ##\n30 days."), "FAQ")
        self.assertEqual([(c.section, c.text) for c in chunks], [("Delivery", "Free over $50"), ("Returns", "30 days.")])
        self.assertIsNone(chunks[0].page)
        self.assertEqual(chunks[0].citation(), "FAQ - Delivery")

    def test_txt_form_feeds_are_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "notes.txt"
            path.write_text("1. Intro\nHello there.\f2. Prices\nTea is $3.", encoding="utf-8")
            chunks = load_file(path)
        self.assertEqual([(c.section, c.page) for c in chunks], [("1. Intro", 1), ("2. Prices", 2)])

    def test_html_skips_navigation_and_scripts(self):
        html = ("<html><head><title>About</title><script>var x=1</script></head><body><nav>Menu</nav>"
                "<main><h2>Team</h2><p>Dr. Lee  works   Mondays.</p></main><footer>(c)</footer></body></html>")
        blocks = html_blocks(html)
        self.assertEqual([(b.text, b.heading) for b in blocks], [("Team", True), ("Dr. Lee works Mondays.", False)])
        self.assertEqual(load_url_html("http://x", html)[0].doc, "About")

    def test_unsupported_file(self):
        with self.assertRaises(ValueError):
            load_file("archive.zip")


class UrlTests(unittest.TestCase):
    def test_fetch_local_page(self):
        with serve_directory(ROOT / "static" / "site") as base:
            html = fetch_url(base + "/team.html")
        chunks = load_url_html(base + "/team.html", html)
        self.assertTrue(any("Polish" in c.text for c in chunks))
        self.assertEqual(chunks[0].doc, "Our Team - Maple Street Dental (demo)")

    def test_rejects_non_http(self):
        for url in ("file:///etc/passwd", "ftp://example.com", "javascript:alert(1)"):
            with self.assertRaises(ValueError):
                fetch_url(url)


class FilenameTests(unittest.TestCase):
    def test_safe_filename(self):
        self.assertEqual(safe_filename("../../etc/Price List.pdf"), "Price List.pdf")
        self.assertEqual(safe_filename("C:\\docs\\menu.docx"), "menu.docx")
        for bad in ("run.exe", "", "..", "notes.pdf.sh"):
            with self.assertRaises(ValueError):
                safe_filename(bad)


if __name__ == "__main__":
    unittest.main()
