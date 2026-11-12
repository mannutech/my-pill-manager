"""Level 2: the extraction agent loop.

Level 1 gave the model one shot. Here the model runs a turn loop and picks
one action per turn, encoded as JSON:

  {"action": "tool", "tool": "lookup_drug", "args": {"name": "amox"}}
  {"action": "tool", "tool": "recrop", "args": {"top":0.2,"left":0,"bottom":0.5,"right":1}}
  {"action": "ask_user", "question": "Does BID mean morning and night?"}
  {"action": "propose", "proposal": {<MedEntry fields>}}

The harness owns the loop: dispatch tools, append results, cap turns,
and validate whatever gets proposed. The model never writes storage.
"""
import io
import json
import uuid

import httpx
from PIL import Image

from .providers import chat
from .schemas import MedEntry

MAX_TURNS = 8

SYSTEM_PROMPT = """You are a prescription-label extraction agent. On each turn
return EXACTLY one JSON object:

- {"action": "tool", "tool": "lookup_drug", "args": {"name": "<partial or full drug name>"}}
  Verify a drug name against the RxNorm database. Use when the label text is
  abbreviated, ambiguous, or possibly misread.
- {"action": "tool", "tool": "recrop", "args": {"top":0,"left":0,"bottom":1,"right":1}}
  Re-examine a cropped region of the image (fractions 0-1). Use when part of
  the label is blurry or dense.
- {"action": "ask_user", "question": "<short question>"}
  Ask the human when a detail can't be resolved from the image.
- {"action": "propose", "proposal": {"name":str,"dose":str,"times_per_day":int,
    "dose_times":["HH:MM"],"quantity_total":int,"confidence":0.0-1.0}}
  Finish once confident. Abbreviations: QD=1, BID=2, TID=3, QID=4 doses/day.

Be economical: propose as soon as you can read the label clearly."""


def lookup_drug(name: str) -> dict:
    """RxNorm approximate-match: is this actually a drug?"""
    resp = httpx.get(
        "https://rxnav.nlm.nih.gov/REST/approximateTerm.json",
        params={"term": name, "maxEntries": 5}, timeout=10,
    )
    candidates = resp.json().get("approximateGroup", {}).get("candidate", [])
    return {"candidates": [
        {"rxcui": c.get("rxcui"), "name": c.get("name"), "score": c.get("score")}
        for c in candidates
    ]}


def recrop(image_bytes: bytes, top: float, left: float,
           bottom: float, right: float) -> tuple[bytes, str]:
    """Crop a fractional region; returned as a new image for the next turn."""
    img = Image.open(io.BytesIO(image_bytes))
    w, h = img.size
    box = (int(left * w), int(top * h), int(right * w), int(bottom * h))
    buf = io.BytesIO()
    img.crop(box).save(buf, format="JPEG")
    return buf.getvalue(), "image/jpeg"


def run_agent(image_bytes: bytes, media_type: str,
              history: list[dict] | None = None,
              allow_ask: bool = True) -> dict:
    """Run the loop. Returns {"type": "proposal"|"question"|"error", ...}.

    `history` lets an ask_user pause resume: the prior message list plus
    the human's answer appended as the last user turn.
    """
    messages = history or [
        {"role": "system", "text": SYSTEM_PROMPT},
        {"role": "user", "text": "Extract this prescription label.",
         "image": (image_bytes, media_type)},
    ]

    for _ in range(MAX_TURNS):
        raw = chat(messages)
        try:
            step = json.loads(raw)
        except json.JSONDecodeError:
            messages.append({"role": "assistant", "text": raw})
            messages.append({"role": "user",
                             "text": "Invalid JSON — return exactly one action object."})
            continue
        messages.append({"role": "assistant", "text": raw})

        action = step.get("action")
        if action == "propose":
            try:
                entry = MedEntry(**step["proposal"])
            except Exception as e:
                messages.append({"role": "user", "text":
                    f"Proposal failed schema validation: {e}. Fix and re-propose."})
                continue
            return {"type": "proposal", "proposal": entry.model_dump(),
                    "turns": len(messages)}

        if action == "ask_user" and allow_ask:
            return {"type": "question", "question": step["question"],
                    "history": messages}

        if action == "tool":
            result, image = _dispatch(step, image_bytes)
            msg = {"role": "user",
                   "text": f"Tool result for {step['tool']}: {json.dumps(result)}"}
            if image:
                msg["image"] = image
            messages.append(msg)
            continue

        messages.append({"role": "user",
                         "text": f"Unknown action '{action}'. Use tool/ask_user/propose."})

    return {"type": "error", "detail": f"agent did not propose within {MAX_TURNS} turns"}


def _dispatch(step: dict, image_bytes: bytes):
    tool, args = step.get("tool"), step.get("args", {})
    if tool == "lookup_drug":
        try:
            return lookup_drug(args.get("name", "")), None
        except Exception as e:
            return {"error": f"lookup failed: {e}"}, None
    if tool == "recrop":
        try:
            img, mt = recrop(image_bytes, **args)
            return {"note": "cropped region attached"}, (img, mt)
        except Exception as e:
            return {"error": f"recrop failed: {e}"}, None
    return {"error": f"unknown tool '{tool}'"}, None


# --- draft sessions: keep the loop's message history between ask_user turns.
# In-memory is fine for a single-process dev app; Level 3+ moves this to a DB.
_drafts: dict[str, dict] = {}


def new_draft(image_bytes: bytes, media_type: str) -> dict:
    draft_id = uuid.uuid4().hex[:8]
    result = run_agent(image_bytes, media_type)
    if result["type"] == "question":
        _drafts[draft_id] = {"image": image_bytes, "media": media_type,
                             "history": result.pop("history")}
        result["draft_id"] = draft_id
    return result


def resume_draft(draft_id: str, answer: str) -> dict:
    draft = _drafts[draft_id]
    history = draft["history"] + [
        {"role": "user", "text": f"Answer to your question: {answer}"}]
    result = run_agent(draft["image"], draft["media"], history=history)
    if result["type"] == "question":
        draft["history"] = result.pop("history")
    else:
        _drafts.pop(draft_id, None)
    return result
