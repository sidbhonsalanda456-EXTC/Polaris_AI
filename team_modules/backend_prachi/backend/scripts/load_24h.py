"""Load the 24-hour CSV datasets into the SQLite database.

Usage (from backend/):
    ..\\.venv\\Scripts\\python scripts\\load_24h.py            # loads all 3 CSVs
    ..\\.venv\\Scripts\\python scripts\\load_24h.py --granularity 1sec

This reads each CSV, validates every row against physical limits, and inserts
valid rows so the demo can query them over the REST API.
"""
import argparse
import csv
import os
import sys
from datetime import datetime

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BASE)

from app.storage.database import Database
from app.schemas import SensorReading
from app.validation.validator import validate_reading

FILES = {
    "1sec": "polar_24h_1sec.csv",
    "1min": "polar_24h_1min.csv",
    "1hour": "polar_24h_1hour.csv",
}
EXTRA_COLS = {"n_seconds", "solar_energy_kwh", "wind_energy_kwh"}


def read_rows(path: str):
    with open(path, "r", encoding="utf-8") as f:
        for raw in csv.DictReader(f):
            row = {k: v for k, v in raw.items() if k not in EXTRA_COLS}
            row["timestamp"] = datetime.strptime(row["timestamp"], "%Y-%m-%d %H:%M:%S").strftime(
                "%Y-%m-%d %H:%M:%S")
            yield row


BATCH = 5000


def main(granularity: str | None):
    db = Database()
    total_accepted = 0
    total_rejected = 0

    targets = [granularity] if granularity else list(FILES.keys())
    for g in targets:
        path = os.path.join(_BASE, "data", FILES[g])
        if not os.path.exists(path):
            print(f"[load] MISSING: {path}. Run scripts/generate_24h.py first.")
            continue
        accepted = 0
        rejected = 0
        pending = []
        for row in read_rows(path):
            try:
                reading = SensorReading(**row)
            except Exception:
                rejected += 1
                continue
            issues = validate_reading(reading)
            if issues:
                rejected += 1
                continue
            pending.append(reading.model_dump())
            if len(pending) >= BATCH:
                db.insert_many(pending)
                accepted += len(pending)
                pending = []
        if pending:
            db.insert_many(pending)
            accepted += len(pending)
        total_accepted += accepted
        total_rejected += rejected
        print(f"[load] {g}: accepted={accepted} rejected={rejected}")

    print(f"\nTotals -> accepted={total_accepted} rejected={total_rejected}")
    print(f"DB now holds {db.count()} raw readings at {db.db_path}")
    db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--granularity", choices=["1sec", "1min", "1hour"], default=None)
    args = ap.parse_args()
    main(args.granularity)