from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from . import agent, storage
from .schemas import MedEntry

app = FastAPI(title="my-pill-manager")
STATIC = Path(__file__).parent.parent / "static"


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.post("/api/extract")
async def extract(photo: UploadFile = File(...)):
    """Step 1: photo -> agent loop -> proposal OR a question for the user.
    Nothing is saved yet — the user confirms via /api/meds."""
    image = await photo.read()
    try:
        return agent.new_draft(image, photo.content_type or "image/jpeg")
    except Exception as e:
        raise HTTPException(422, f"Could not parse label: {e}")


@app.post("/api/extract/{draft_id}/answer")
def answer(draft_id: str, body: dict):
    """Resume a paused agent loop with the user's answer."""
    if draft_id not in agent._drafts:
        raise HTTPException(404, "draft expired or unknown")
    return agent.resume_draft(draft_id, body.get("answer", ""))


@app.post("/api/meds")
def confirm_med(entry: MedEntry):
    """Step 2: user-confirmed (possibly edited) entry -> storage."""
    return storage.add_med(entry)


@app.get("/api/meds")
def get_meds():
    meds = storage.list_meds()
    return {
        "meds": meds,
        "low_stock": [m for m in meds
                      if m.quantity_remaining <= 7 * m.times_per_day],
    }


@app.post("/api/meds/{med_id}/taken")
def took(med_id: str):
    med = storage.mark_taken(med_id)
    if not med:
        raise HTTPException(404, "med not found or already empty")
    return med


app.mount("/static", StaticFiles(directory=STATIC), name="static")
