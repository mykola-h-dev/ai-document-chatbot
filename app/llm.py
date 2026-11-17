"""Minimal LLM client for Google Gemini or OpenAI, using only `requests`.

The provider is chosen from environment variables:
  - GEMINI_API_KEY  -> Google Gemini (model from GEMINI_MODEL, default gemini-3.5-flash)
  - OPENAI_API_KEY  -> OpenAI Chat Completions (model from OPENAI_MODEL, default gpt-4o-mini)
If neither is set, `is_available()` returns False and callers fall back to offline mode.
`stream()` yields the reply piece by piece (Server-Sent Events from either API).
Keys are never logged or printed.
"""

import json
import os

import requests

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GEMINI_STREAM_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent?alt=sse"
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
TIMEOUT_SECONDS = 30


def provider_name():
    """Return 'gemini', 'openai' or None depending on which key is configured."""
    if os.environ.get("GEMINI_API_KEY"):
        return "gemini"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    return None


def is_available():
    return provider_name() is not None


def generate(system_prompt, user_prompt, temperature=0.2):
    """Send one prompt to the configured provider and return the reply text.

    Raises RuntimeError when no key is configured or the API call fails,
    so the caller can decide to fall back to offline mode.
    """
    provider = provider_name()
    try:
        if provider == "gemini":
            return _gemini(system_prompt, user_prompt, temperature)
        if provider == "openai":
            return _openai(system_prompt, user_prompt, temperature)
    except requests.RequestException as exc:  # network errors, timeouts
        raise RuntimeError(f"LLM request failed: {type(exc).__name__}") from exc
    raise RuntimeError("No LLM API key configured")


def _gemini(system_prompt, user_prompt, temperature):
    model = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
    body = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": {"temperature": temperature},
    }
    headers = {"x-goog-api-key": os.environ["GEMINI_API_KEY"], "Content-Type": "application/json"}
    resp = requests.post(GEMINI_URL.format(model=model), json=body, headers=headers, timeout=TIMEOUT_SECONDS)
    if resp.status_code != 200:
        raise RuntimeError(f"Gemini API error {resp.status_code}")
    data = resp.json()
    try:
        parts = data["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts).strip()
    except (KeyError, IndexError) as exc:
        raise RuntimeError("Unexpected Gemini response format") from exc


def _openai(system_prompt, user_prompt, temperature):
    body = {
        "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    headers = {"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"}
    resp = requests.post(OPENAI_URL, json=body, headers=headers, timeout=TIMEOUT_SECONDS)
    if resp.status_code != 200:
        raise RuntimeError(f"OpenAI API error {resp.status_code}")
    try:
        return resp.json()["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, ValueError) as exc:
        raise RuntimeError("Unexpected OpenAI response format") from exc


def stream(system_prompt, user_prompt, temperature=0.2):
    """Yield the reply in pieces as the provider produces them.

    Raises RuntimeError (before or during iteration) on any failure, so the
    caller can fall back to a non-streamed or offline answer.
    """
    provider = provider_name()
    if provider is None:
        raise RuntimeError("No LLM API key configured")
    try:
        if provider == "gemini":
            yield from _gemini_stream(system_prompt, user_prompt, temperature)
        else:
            yield from _openai_stream(system_prompt, user_prompt, temperature)
    except requests.RequestException as exc:
        raise RuntimeError(f"LLM request failed: {type(exc).__name__}") from exc


def _sse_data(resp):
    """Yield the JSON payload of every `data:` line of a Server-Sent Events response."""
    for line in resp.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            return
        try:
            yield json.loads(data)
        except json.JSONDecodeError:
            continue


def _gemini_stream(system_prompt, user_prompt, temperature):
    model = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
    body = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": {"temperature": temperature},
    }
    headers = {"x-goog-api-key": os.environ["GEMINI_API_KEY"], "Content-Type": "application/json"}
    with requests.post(GEMINI_STREAM_URL.format(model=model), json=body, headers=headers,
                       timeout=TIMEOUT_SECONDS, stream=True) as resp:
        if resp.status_code != 200:
            raise RuntimeError(f"Gemini API error {resp.status_code}")
        for event in _sse_data(resp):
            for cand in event.get("candidates", [])[:1]:
                for part in cand.get("content", {}).get("parts", []):
                    if part.get("text"):
                        yield part["text"]


def _openai_stream(system_prompt, user_prompt, temperature):
    body = {
        "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        "temperature": temperature,
        "stream": True,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    headers = {"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"}
    with requests.post(OPENAI_URL, json=body, headers=headers, timeout=TIMEOUT_SECONDS, stream=True) as resp:
        if resp.status_code != 200:
            raise RuntimeError(f"OpenAI API error {resp.status_code}")
        for event in _sse_data(resp):
            for choice in event.get("choices", [])[:1]:
                text = (choice.get("delta") or {}).get("content")
                if text:
                    yield text
