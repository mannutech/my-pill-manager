"""Provider-agnostic chat for the agent loop.

Level 1's llm.py was one-shot: image in, JSON out. The agent loop needs
multi-turn chat where tool results are fed back as new messages. This
module owns one internal message format and converts per provider.

Internal message: {"role": "user"|"assistant", "text": str,
                   "image": (bytes, media_type) | None}
"""
import base64
import json
import os


def provider() -> str:
    return os.getenv("LLM_PROVIDER", "mock")


def chat(messages: list[dict]) -> str:
    """One assistant turn. Returns the model's raw text."""
    fn = {
        "anthropic": _chat_anthropic,
        "openai": _chat_openai,
        "ollama": _chat_ollama,
        "mock": _chat_mock,
    }[provider()]
    return fn(messages)


def _chat_mock(messages: list[dict]) -> str:
    # Deterministic fake agent: propose immediately, ignoring the image.
    return json.dumps({
        "action": "propose",
        "proposal": {
            "name": "Amoxicillin", "dose": "500mg", "times_per_day": 2,
            "dose_times": ["08:00", "20:00"], "quantity_total": 20,
            "confidence": 0.9,
        },
    })


def _chat_ollama(messages: list[dict]) -> str:
    import httpx

    def convert(m):
        out = {"role": m["role"], "content": m["text"]}
        if m.get("image"):
            out["images"] = [base64.b64encode(m["image"][0]).decode()]
        return out

    resp = httpx.post(
        os.getenv("OLLAMA_HOST", "http://localhost:11434") + "/api/chat",
        json={
            "model": os.getenv("OLLAMA_MODEL", "qwen2.5vl:3b"),
            "messages": [convert(m) for m in messages],
            "format": "json",
            "stream": False,
        },
        timeout=180,
    )
    resp.raise_for_status()
    return resp.json()["message"]["content"]


def _chat_openai(messages: list[dict]) -> str:
    import openai

    def convert(m):
        content = [{"type": "text", "text": m["text"]}]
        if m.get("image"):
            b64 = base64.b64encode(m["image"][0]).decode()
            content.append({"type": "image_url", "image_url": {
                "url": f"data:{m['image'][1]};base64,{b64}"}})
        return {"role": m["role"], "content": content}

    resp = openai.OpenAI().chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4o"),
        response_format={"type": "json_object"},
        messages=[convert(m) for m in messages],
    )
    return resp.choices[0].message.content


def _chat_anthropic(messages: list[dict]) -> str:
    import anthropic

    def convert(m):
        content = []
        if m.get("image"):
            content.append({"type": "image", "source": {
                "type": "base64", "media_type": m["image"][1],
                "data": base64.b64encode(m["image"][0]).decode()}})
        content.append({"type": "text", "text": m["text"]})
        return {"role": m["role"], "content": content}

    msg = anthropic.Anthropic().messages.create(
        model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5"),
        max_tokens=1024,
        system=messages[0]["text"] if messages[0]["role"] == "system" else None,
        messages=[convert(m) for m in messages if m["role"] != "system"],
    )
    return next(b.text for b in msg.content if b.type == "text")
