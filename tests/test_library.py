import pathlib
import tempfile
import unittest

from tests.helpers import SAMPLES
from app.library import Library

PAGE = "<html><head><title>Menu</title></head><body><main><h2>Lunch</h2><p>Soup of the day is $6.</p></main></body></html>"


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pages = {"http://shop.test/menu": PAGE}
        self.lib = Library(self.tmp.name, SAMPLES, fetch=self.fake_fetch)

    def tearDown(self):
        self.tmp.cleanup()

    def fake_fetch(self, url):
        if url not in self.pages:
            raise ConnectionError("offline")
        return self.pages[url]

    def test_seed_copied_once(self):
        names = [p.name for p in self.lib.files()]
        self.assertEqual(sorted(names), ["aftercare-sheet.docx", "new-patient-faq.md", "patient-guide.pdf"])
        self.lib.remove("new-patient-faq.md")
        again = Library(self.tmp.name, SAMPLES)  # restart must not re-seed removed files
        self.assertNotIn("new-patient-faq.md", [p.name for p in again.files()])

    def test_upload_and_remove(self):
        before = len(self.lib.chunks)
        name = self.lib.add_file("Holiday Hours.txt", b"1. Christmas\nClosed 24 to 27 December.")
        self.assertEqual(name, "Holiday Hours.txt")
        self.assertGreater(len(self.lib.chunks), before)
        self.assertIn("Holiday Hours", {c.doc for c in self.lib.chunks})
        self.lib.remove(name)
        self.assertEqual(len(self.lib.chunks), before)

    def test_broken_upload_rejected_and_not_kept(self):
        with self.assertRaises(ValueError):
            self.lib.add_file("broken.docx", b"this is not a zip")
        self.assertFalse((pathlib.Path(self.tmp.name) / "docs" / "broken.docx").exists())

    def test_remove_unknown(self):
        with self.assertRaises(KeyError):
            self.lib.remove("missing.pdf")

    def test_url_source_survives_restart_and_failed_refetch(self):
        self.assertEqual(self.lib.add_url("http://shop.test/menu"), "Menu")
        self.assertTrue(any("Soup" in c.text for c in self.lib.chunks))
        restarted = Library(self.tmp.name, SAMPLES, fetch=self.fake_fetch)  # cached copy, no download
        self.assertTrue(any("Soup" in c.text for c in restarted.chunks))
        self.pages.clear()  # the site goes down
        restarted.reindex(refetch=True)
        self.assertIn("http://shop.test/menu", restarted.errors)
        self.assertTrue(any("Soup" in c.text for c in restarted.chunks))  # old copy kept
        sources = {s["name"]: s for s in restarted.list_sources()}
        self.assertEqual(sources["http://shop.test/menu"]["kind"], "url")
        self.assertTrue(sources["http://shop.test/menu"]["error"])
        restarted.remove("http://shop.test/menu")
        self.assertFalse(any("Soup" in c.text for c in restarted.chunks))

    def test_refetch_updates_page(self):
        self.lib.add_url("http://shop.test/menu")
        self.pages["http://shop.test/menu"] = PAGE.replace("$6", "$7")
        self.lib.reindex(refetch=True)
        self.assertTrue(any("$7" in c.text for c in self.lib.chunks))


if __name__ == "__main__":
    unittest.main()
