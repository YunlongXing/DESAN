#!/usr/bin/env python3
"""Rewrite SanRazor comparison summaries using Detected Disabled as removed.

The SanRazor check.txt "removed" value is an internal SC accounting number.
For our comparison tables, the removed-check count should be the number of
UBSan handler paths actually disabled in the transformed IR, as produced by
sanrazor_removed_access_summary.py.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary-csv", required=True)
    parser.add_argument("--access-csv", required=True)
    parser.add_argument("--csv-out", required=True)
    parser.add_argument("--md-out", required=True)
    return parser.parse_args()


def number(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def float_number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def fmt_int(value):
    return f"{int(value):,}"


def fmt_float(value):
    value = float_number(value)
    return "--" if value is None else f"{value:.3f}"


def fmt_pct(value):
    value = float_number(value)
    return "--" if value is None else f"{value:.2f}%"


def read_access(path: Path):
    access = {}
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            bench = row.get("Benchmark", "")
            if not bench or bench == "TOTAL":
                continue
            key = (row.get("Level", ""), bench)
            access[key] = row
    return access


def main():
    args = parse_args()
    summary_csv = Path(args.summary_csv)
    access = read_access(Path(args.access_csv))

    with summary_csv.open(newline="") as f:
        rows = list(csv.DictReader(f))

    out_rows = []
    for row in rows:
        key = (row.get("SanRazor Level", ""), row.get("Benchmark", ""))
        access_row = access.get(key)
        if not access_row:
            out_rows.append(row)
            continue

        original = number(row.get("Original Checks"))
        reported_removed = number(row.get("Removed Checks"))
        detected_removed = number(access_row.get("Removed Checks"))

        row = dict(row)
        row["SanRazor Reported Removed Checks"] = reported_removed
        row["Detected / Reported"] = access_row.get("Detected / Reported", "")
        row["Removed Checks"] = detected_removed
        row["SanRazor Checks"] = max(0, original - detected_removed)
        row["Removed / Original"] = (
            detected_removed / original * 100.0 if original else None
        )
        row["Removed READ Checks"] = number(access_row.get("Removed READ Checks"))
        row["Removed WRITE Checks"] = number(access_row.get("Removed WRITE Checks"))
        row["Removed UNKNOWN Checks"] = number(access_row.get("Removed UNKNOWN Checks"))
        row["READ / Removed"] = access_row.get("READ / Removed", "")
        row["WRITE / Removed"] = access_row.get("WRITE / Removed", "")
        row["UNKNOWN / Removed"] = access_row.get("UNKNOWN / Removed", "")
        out_rows.append(row)

    preferred = [
        "Suite",
        "Benchmark",
        "SanRazor Level",
        "Original Checks",
        "SanRazor Checks",
        "Removed Checks",
        "Removed / Original",
        "SanRazor Reported Removed Checks",
        "Detected / Reported",
        "Removed READ Checks",
        "Removed WRITE Checks",
        "Removed UNKNOWN Checks",
        "READ / Removed",
        "WRITE / Removed",
        "UNKNOWN / Removed",
    ]
    fieldnames = []
    for field in preferred + list(out_rows[0].keys()):
        if field in out_rows[0] and field not in fieldnames:
            fieldnames.append(field)

    csv_out = Path(args.csv_out)
    csv_out.parent.mkdir(parents=True, exist_ok=True)
    with csv_out.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(out_rows)

    md_out = Path(args.md_out)
    md_out.parent.mkdir(parents=True, exist_ok=True)
    with md_out.open("w") as f:
        f.write(
            "| Benchmark | Original | SanRazor | Removed | Removed/Orig | Read | Write | Unknown | Write/Removed | Native(s) | UBSan(s) | SanRazor(s) | Overhead Reduction | Status |\n"
        )
        f.write("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|\n")
        for row in out_rows:
            f.write(
                "| "
                + " | ".join(
                    [
                        row["Benchmark"],
                        fmt_int(row["Original Checks"]),
                        fmt_int(row["SanRazor Checks"]),
                        fmt_int(row["Removed Checks"]),
                        fmt_pct(row["Removed / Original"]),
                        fmt_int(row.get("Removed READ Checks", 0)),
                        fmt_int(row.get("Removed WRITE Checks", 0)),
                        fmt_int(row.get("Removed UNKNOWN Checks", 0)),
                        row.get("WRITE / Removed", "--"),
                        fmt_float(row["Runtime Native"]),
                        fmt_float(row["Runtime UBSan"]),
                        fmt_float(row["Runtime SanRazor"]),
                        fmt_pct(row["Overhead Reduction %"]),
                        f'{row["Native Status"]}->{row["UBSan Status"]}->{row["SanRazor Status"]}',
                    ]
                )
                + " |\n"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
