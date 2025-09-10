#!/usr/bin/env python3
"""Generate a compact JSON file for the dashboard from report/compliance-report.csv.

Outputs docs/compliance-report.json (array of objects) with pre-split message arrays
so the browser doesn't need to parse a large CSV or split multi-line strings.

Run:
  python prepare_dashboard_json.py
"""
from __future__ import annotations
import csv
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).parent
CSV_PATH = ROOT / "report" / "compliance-report.csv"
OUT_PATH = ROOT / "docs" / "compliance-report.json"

# Columns that contain multiline message blocks.
MESSAGE_COLUMNS = [
    "cf:low_priorities",
    "cf:medium_priorities",
    "cf:high_priorities",
    "cc6:low_priorities",
    "cc6:medium_priorities",
    "cc6:high_priorities",
]


def split_messages(val: str | None):
    if not val:
        return []
    # Split on newlines, trim, keep non-empty
    return [line.strip() for line in val.splitlines() if line.strip()]


def main():
    if not CSV_PATH.exists():
        print(f"ERROR: CSV not found: {CSV_PATH}", file=sys.stderr)
        return 1
    rows = []
    with CSV_PATH.open("r", newline="") as f:
        reader = csv.DictReader(f)
        for raw in reader:
            # Build compact record
            rec = {
                "filename": raw.get("filename"),
                "variable_id": raw.get("variable_id"),
                "institution_id": raw.get("institution_id"),
                "source_id": raw.get("source_id"),
                "driving_source_id": raw.get("driving_source_id"),
                "driving_experiment_id": raw.get("driving_experiment_id"),
                "frequency": raw.get("frequency"),
                "cf_scored": safe_float(raw.get("cf:scored_points")),
                "cf_possible": safe_float(raw.get("cf:possible_points")),
                "cf_high_count": safe_int(raw.get("cf:high_count")),
                "cf_medium_count": safe_int(raw.get("cf:medium_count")),
                "cf_low_count": safe_int(raw.get("cf:low_count")),
                "cc6_scored": safe_float(raw.get("cc6:scored_points")),
                "cc6_possible": safe_float(raw.get("cc6:possible_points")),
                "cc6_high_count": safe_int(raw.get("cc6:high_count")),
                "cc6_medium_count": safe_int(raw.get("cc6:medium_count")),
                "cc6_low_count": safe_int(raw.get("cc6:low_count")),
            }
            # Add message arrays only if non-empty
            cf_low = split_messages(raw.get("cf:low_priorities"))
            cf_med = split_messages(raw.get("cf:medium_priorities"))
            cf_high = split_messages(raw.get("cf:high_priorities"))
            cc6_low = split_messages(raw.get("cc6:low_priorities"))
            cc6_med = split_messages(raw.get("cc6:medium_priorities"))
            cc6_high = split_messages(raw.get("cc6:high_priorities"))
            if cf_low:
                rec["cf_low"] = cf_low
            if cf_med:
                rec["cf_med"] = cf_med
            if cf_high:
                rec["cf_high"] = cf_high
            if cc6_low:
                rec["cc6_low"] = cc6_low
            if cc6_med:
                rec["cc6_med"] = cc6_med
            if cc6_high:
                rec["cc6_high"] = cc6_high
            rec["hasHigh"] = bool(cf_high or cc6_high)
            rows.append(rec)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Write pretty small (no indentation) to minimize size
    with OUT_PATH.open("w") as out:
        json.dump(rows, out, ensure_ascii=False, separators=(",", ":"))
    print(
        f"Wrote {len(rows)} records -> {OUT_PATH} ({OUT_PATH.stat().st_size/1024:.1f} KiB)"
    )
    return 0


def safe_float(v):
    try:
        return float(v) if v not in (None, "") else None
    except Exception:
        return None


def safe_int(v):
    try:
        return int(float(v)) if v not in (None, "") else None
    except Exception:
        return None


if __name__ == "__main__":
    raise SystemExit(main())
