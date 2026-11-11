# my-pill-manager

Snap a photo of a prescription label → it becomes a tracked med → the app
counts your stock down and reminds you when a dose is due.

Built level-by-level as a harness-engineering exercise: each level adds one
real AI-engineering concept on top of the same ordinary web app. Check out a
tag to see the app at that stage; `main` is always the latest level.

## Level map

| Tag | Adds | Core lesson |
|-----|------|-------------|
| `level-1` | Photo → structured JSON → confirm → save; stock countdown; eval set | Structured output + validation + evals |
| `level-2` | Agent loop with tools (drug lookup, re-read crop, ask_user) | Tool use, stopping conditions, cost control |
| `level-3` | Adherence memory + summarization | Context/memory design |
| `level-4` | Refill agent vs single-prompt comparison | When delegation pays off (rarely) |
| `level-5` | Turn logging, eval dashboard, CI gates | Observability |

Each level's writeup — what was learned, how it maps to real products, and
why the next level exists — lives in `docs/LEVEL-N.md`.

## Run it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # LLM_PROVIDER=mock works with no API key
uvicorn app.main:app --reload
```

Open http://localhost:8000 — upload a label photo, confirm the parsed
fields, then "Took it" decrements stock. Meds are stored in
`data/meds.json`.

## The one rule that runs through every level

**The LLM proposes, code disposes.** The model can never write to the med
table directly — it produces a proposal that passes schema validation and
a human confirm before anything is stored.

## Evals

```bash
python -m evals.run_eval
```

Drop `photos/<name>.jpg` + `expected/<name>.json` pairs in `evals/` and
this prints per-field accuracy. Run it after every prompt/schema change.
