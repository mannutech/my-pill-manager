from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from . import storage
from .llm import extract_med
from .schemas import MedEntry

app = FastAPI(title="my-pill-manager")
STATIC = Path(__file__).parent.parent / "static"


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.post("/api/extract")
async def extract(photo: UploadFile = File(...)):
    """Step 1: photo -> proposed MedEntry. Nothing is saved yet —
    the user must confirm via /api/meds. The LLM proposes, code disposes."""
    image = await photo.read()
    try:
        proposal = extract_med(image, photo.content_type or "image/jpeg")
    except Exception as e:
        raise HTTPException(422, f"Could not parse label: {e}")
    return {"proposal": proposal.model_dump()}


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
