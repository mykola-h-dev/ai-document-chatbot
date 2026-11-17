"""Pure-Python BM25 retrieval over document chunks.

BM25 is the classic ranking function used by search engines such as
Elasticsearch. It needs no external libraries and works well for short
business documents (FAQs, price lists, policies).
"""

import math
import re
from collections import Counter

STOPWORDS = set("""
a an and are as at be by can do does for from have how i if in is it me my of on or our
please so that the this to us we what when where which who why will with you your
offer offers provide need want get any there tell know about
""".split())

# Small, editable synonym map: words customers use -> words the document uses.
SYNONYMS = {
    "cost": "price", "costs": "price", "much": "price", "fee": "price", "charge": "price",
    "open": "hours", "opening": "hours", "close": "hours", "closed": "hours", "time": "hours",
    "park": "parking", "car": "parking",
    "appointment": "booking", "book": "booking", "schedule": "booking",
    "cancel": "cancellation", "reschedule": "cancellation",
    "pay": "payment", "card": "payment", "installments": "payment", "plan": "payment",
    "urgent": "emergency", "pain": "emergency", "toothache": "emergency",
    "kids": "children", "child": "children", "kid": "children",
    "address": "location", "where": "location", "located": "location",
    "phone": "contact", "email": "contact", "call": "contact",
    "weekend": "saturday", "late": "notice",
}

TOKEN_RE = re.compile(r"[a-z0-9$]+")


def _stem(word):
    """Very light stemming so 'prices' matches 'price' and 'booking' matches 'book'."""
    for suffix in ("ings", "ing", "es", "s"):
        if len(word) > len(suffix) + 2 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def tokenize(text, expand=False):
    tokens = []
    for word in TOKEN_RE.findall(text.lower()):
        if expand and word in SYNONYMS:
            tokens.append(_stem(SYNONYMS[word]))
        if word not in STOPWORDS:
            tokens.append(_stem(word))
    return tokens


class BM25Index:
    def __init__(self, chunks, k1=1.5, b=0.75):
        self.chunks = chunks
        self.k1, self.b = k1, b
        # Section titles are repeated (boosted) so "opening hours" finds the hours section first.
        self.doc_tokens = [tokenize(f"{c.section} {c.section} {c.section} {c.text}") for c in chunks]
        self.doc_freqs = [Counter(toks) for toks in self.doc_tokens]
        self.avg_len = sum(len(t) for t in self.doc_tokens) / max(len(chunks), 1)
        self.idf = self._compute_idf()

    def _compute_idf(self):
        df = Counter()
        for toks in self.doc_tokens:
            df.update(set(toks))
        n = len(self.doc_tokens)
        return {term: math.log(1 + (n - freq + 0.5) / (freq + 0.5)) for term, freq in df.items()}

    def score(self, query_tokens, idx):
        freqs = self.doc_freqs[idx]
        length = len(self.doc_tokens[idx])
        total = 0.0
        for term in query_tokens:
            if term not in freqs:
                continue
            tf = freqs[term]
            norm = tf * (self.k1 + 1) / (tf + self.k1 * (1 - self.b + self.b * length / self.avg_len))
            total += self.idf.get(term, 0.0) * norm
        return total

    def search(self, query, top_k=3):
        """Return [(score, chunk), ...] sorted best first, skipping zero scores."""
        query_tokens = tokenize(query, expand=True)
        scored = [(self.score(query_tokens, i), c) for i, c in enumerate(self.chunks)]
        scored = [pair for pair in scored if pair[0] > 0]
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return scored[:top_k]
