"""Offline tests: python -m unittest discover tests"""

import os
import pathlib
import unittest

os.environ.pop("GEMINI_API_KEY", None)
os.environ.pop("OPENAI_API_KEY", None)

from app.answerer import answer  # noqa: E402
from app.pdf_loader import load_document  # noqa: E402
from app.retriever import BM25Index  # noqa: E402

PDF = pathlib.Path(__file__).resolve().parent.parent / "sample_docs" / "maple-street-dental-guide.pdf"


class ChatbotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = BM25Index(load_document(PDF))

    def ask(self, question):
        return answer(question, self.index, "Maple Street Dental", "call 555-0142")

    def test_pdf_has_sections_on_three_pages(self):
        self.assertEqual({c.page for c in self.index.chunks}, {1, 2, 3})

    def test_price_question_cites_page_2(self):
        result = self.ask("How much is a root canal?")
        self.assertIn("$650", result["answer"])
        self.assertIn("page 2", result["sources"][0])

    def test_opening_hours(self):
        result = self.ask("What are your opening hours?")
        self.assertIn("Saturday", result["answer"])
        self.assertTrue(result["sources"][0].startswith("2. Opening Hours"))

    def test_unknown_question_is_refused(self):
        for question in ("Do you offer veneers?", "What is the capital of France?"):
            result = self.ask(question)
            self.assertFalse(result["found"], question)
            self.assertIn("contact", result["answer"].lower())


if __name__ == "__main__":
    unittest.main()
