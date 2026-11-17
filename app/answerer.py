"""Turn retrieved chunks into an answer with a page citation.

Two modes:
  - AI mode (GEMINI_API_KEY or OPENAI_API_KEY set): the LLM writes a short answer
    using ONLY the retrieved passages.
  - Offline demo mode (no key): the most relevant sentences from the best passage
    are returned word for word.
In both modes, if the document does not contain the answer, the bot says so and
points the visitor to the business contact details instead of guessing.
"""

import re

from . import llm
from .retriever import tokenize

MIN_SCORE = 1.2          # below this, we treat the question as "not in the document"
NOT_FOUND_TOKEN = "NOT_FOUND"
SHORT_SECTION_WORDS = 45  # short sections matching the question are returned in full

SYSTEM_PROMPT = (
    "You are the website assistant for {business}. Answer the visitor's question using ONLY "
    "the numbered passages provided. Keep answers to 1-3 friendly sentences. Do not invent "
    "prices, times or policies. If the passages do not contain the answer, reply with exactly "
    f"{NOT_FOUND_TOKEN}."
)


def fallback_message(business, contact):
    return (f"Sorry, I couldn't find that in the {business} guide. "
            f"Please contact the team directly{': ' + contact if contact else ''} and they will be happy to help.")


def answer(question, index, business, contact=""):
    """Return a dict: {answer, sources: [..], mode, found}."""
    results = index.search(question, top_k=3)
    mode = "ai" if llm.is_available() else "offline"
    if not results or results[0][0] < MIN_SCORE:
        return _not_found(business, contact, mode)

    if mode == "ai":
        try:
            return _ai_answer(question, results, business, contact)
        except RuntimeError:
            mode = "offline (AI unavailable)"
    return _offline_answer(question, results, mode)


def _not_found(business, contact, mode):
    return {"answer": fallback_message(business, contact), "sources": [], "mode": mode, "found": False}


def _ai_answer(question, results, business, contact):
    passages = "\n\n".join(
        f"[{i}] ({chunk.citation()}) {chunk.text}" for i, (_, chunk) in enumerate(results, start=1)
    )
    prompt = f"Passages:\n{passages}\n\nVisitor question: {question}"
    reply = llm.generate(SYSTEM_PROMPT.format(business=business), prompt)
    if NOT_FOUND_TOKEN in reply:
        return _not_found(business, contact, "ai")
    return {"answer": reply, "sources": [c.citation() for _, c in results[:2]], "mode": "ai", "found": True}


def _offline_answer(question, results, mode):
    best_chunk = results[0][1]
    query_terms = set(tokenize(question, expand=True))
    asks_whole_section = bool(query_terms & set(tokenize(best_chunk.section)))
    if asks_whole_section and len(best_chunk.text.split()) <= SHORT_SECTION_WORDS:
        text = best_chunk.text  # e.g. "opening hours": the whole short section is the answer
    else:
        text = " ".join(_best_sentences(question, best_chunk.text))
    return {"answer": text, "sources": [best_chunk.citation()], "mode": mode, "found": True}


def _best_sentences(question, text, limit=2):
    """Pick the sentences of a passage that share the most words with the question."""
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    query_terms = set(tokenize(question, expand=True))
    ranked = sorted(
        enumerate(sentences),
        key=lambda pair: len(query_terms & set(tokenize(pair[1]))),
        reverse=True,
    )
    top = [pair for pair in ranked[:limit] if query_terms & set(tokenize(pair[1]))] or ranked[:1]
    return [sentences[i] for i, _ in sorted(top)]  # keep original order for readability
