"""Eval harness: run extraction over evals/photos against evals/expected.

Drop a label photo in photos/ and a same-named JSON of the correct answer
in expected/ (e.g. photos/amox.jpg + expected/amox.json). Then:

    python -m evals.run_eval

Run this after EVERY prompt or schema change — that's the whole point:
prompt edits are code changes, and this is the test suite for them.
"""
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.agent import run_agent  # noqa: E402

PHOTOS = Path(__file__).parent / "photos"
EXPECTED = Path(__file__).parent / "expected"
FIELDS = ["name", "dose", "times_per_day", "dose_times", "quantity_total"]


def score(got: dict, want: dict) -> dict:
    return {
        f: (str(got.get(f, "")).lower().strip()
            == str(want.get(f, "")).lower().strip())
        for f in FIELDS
    }


def main() -> int:
    cases = sorted(EXPECTED.glob("*.json"))
    if not cases:
        print("No eval cases yet — add expected/*.json + photos/*")
        return 0

    total_correct = total_fields = 0
    for exp_file in cases:
        stem = exp_file.stem
        photo = next(iter(PHOTOS.glob(f"{stem}.*")), None)
        if not photo:
            print(f"SKIP {stem}: no matching photo")
            continue
        want = json.loads(exp_file.read_text())
        media = "image/png" if photo.suffix == ".png" else "image/jpeg"
        try:
            result = run_agent(photo.read_bytes(), media, allow_ask=False)
            if result["type"] != "proposal":
                print(f"FAIL {stem}: agent returned {result['type']} "
                      f"({result.get('detail', '')})")
                continue
            got = result["proposal"]
        except Exception as e:
            print(f"FAIL {stem}: extraction raised {e}")
            continue
        results = score(got, want)
        ok = sum(results.values())
        total_correct += ok
        total_fields += len(FIELDS)
        mark = " ".join(f"{f}:{'ok' if v else 'MISS'}" for f, v in results.items())
        print(f"{stem}: {ok}/{len(FIELDS)}  {mark}")

    if total_fields:
        print(f"\nField accuracy: {total_correct}/{total_fields} "
              f"({100 * total_correct / total_fields:.0f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
