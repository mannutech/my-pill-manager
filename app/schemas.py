from pydantic import BaseModel, Field


class MedEntry(BaseModel):
    """What the LLM proposes AND what gets stored. One schema, two uses:
    the extractor must produce this shape, and the DB stores it verbatim
    after user confirmation."""

    name: str
    dose: str = Field(description="e.g. '500mg' or '1 tablet'")
    times_per_day: int = Field(ge=1, le=6)
    dose_times: list[str] = Field(
        description="Local times 'HH:MM' — e.g. ['08:00','20:00'] for 2x/day"
    )
    quantity_total: int = Field(gt=0, description="pills dispensed")
    confidence: float = Field(ge=0.0, le=1.0)


class Med(MedEntry):
    id: str
    quantity_remaining: int
