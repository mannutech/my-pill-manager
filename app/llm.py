"""Provider-agnostic vision extraction.

The whole 'AI feature' is this one function: image bytes -> validated MedEntry.
Swap providers by setting LLM_PROVIDER; the interface stays the same.
`mock` returns canned data so the app and evals run without API keys.
"""
import base64
import json
import os

from .schemas import MedEntry

EXTRACTION_PROMPT = """Read this prescription / pill-bottle label photo.
Return ONLY JSON matching this schema:
{"name": str, "dose": str like "500mg", "times_per_day": int,
 "dose_times": ["HH:MM", ...], "quantity_total": int,
 "confidence": 0.0-1.0}
Rules:
- dose_times: spread doses sensibly (1x/day -> ["08:00"], 2x -> ["08:00","20:00"]).
- If a field is unreadable, lower confidence rather than guessing.
- Abbreviations: QD/once daily=1, BID=2, TID=3, QID=4.
"""


def extract_med(image_bytes: bytes, media_type: str = "image/jpeg") -> MedEntry:
    provider = os.getenv("LLM_PROVIDER", "mock")
    raw = {
        "anthropic": _extract_anthropic,
        "openai": _extract_openai,
        "ollama": _extract_ollama,
        "mock": _extract_mock,
    }[provider](image_bytes, media_type)
    # The harness boundary: whatever the model returned, it must pass
    # the schema (and our sanity rules) before it touches storage.
    return MedEntry(**json.loads(raw))


def _extract_mock(image_bytes: bytes, media_type: str) -> str:
    return json.dumps({
        "name": "Amoxicillin",
        "dose": "500mg",
        "times_per_day": 2,
        "dose_times": ["08:00", "20:00"],
        "quantity_total": 20,
        "confidence": 0.9,
    })


def _extract_anthropic(image_bytes: bytes, media_type: str) -> str:
    import anthropic

    client = anthropic.Anthropic()
    msg = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {
                    "type": "base64", "media_type": media_type,
                    "data": base64.b64encode(image_bytes).decode()}},
                {"type": "text", "text": EXTRACTION_PROMPT},
            ],
        }],
    )
    text = next(b.text for b in msg.content if b.type == "text")
    return text


def _extract_ollama(image_bytes: bytes, media_type: str) -> str:
    import httpx

    resp = httpx.post(
        os.getenv("OLLAMA_HOST", "http://localhost:11434") + "/api/generate",
        json={
            "model": os.getenv("OLLAMA_MODEL", "qwen2.5vl:3b"),
            "prompt": EXTRACTION_PROMPT,
            "images": [base64.b64encode(image_bytes).decode()],
            "format": "json",
            "stream": False,
        },
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["response"]


def _extract_openai(image_bytes: bytes, media_type: str) -> str:
    import openai

    client = openai.OpenAI()
    b64 = base64.b64encode(image_bytes).decode()
    resp = client.chat.completions.create(
        model="gpt-4o",
        response_format={"type": "json_object"},
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": EXTRACTION_PROMPT},
                {"type": "image_url", "image_url": {
                    "url": f"data:{media_type};base64,{b64}"}},
            ],
        }],
    )
    return resp.choices[0].message.content
