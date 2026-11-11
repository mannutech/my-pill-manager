import json
import uuid
from pathlib import Path

from .schemas import Med, MedEntry

DATA_FILE = Path(__file__).parent.parent / "data" / "meds.json"


def _load() -> list[dict]:
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text())
    return []


def _save(meds: list[dict]) -> None:
    DATA_FILE.parent.mkdir(exist_ok=True)
    DATA_FILE.write_text(json.dumps(meds, indent=2))


def list_meds() -> list[Med]:
    return [Med(**m) for m in _load()]


def add_med(entry: MedEntry) -> Med:
    med = Med(id=uuid.uuid4().hex[:8], quantity_remaining=entry.quantity_total,
              **entry.model_dump())
    meds = _load()
    meds.append(med.model_dump())
    _save(meds)
    return med


def mark_taken(med_id: str) -> Med | None:
    meds = _load()
    for m in meds:
        if m["id"] == med_id and m["quantity_remaining"] > 0:
            m["quantity_remaining"] -= 1
            _save(meds)
            return Med(**m)
    return None
