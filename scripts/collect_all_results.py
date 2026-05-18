#!/usr/bin/env python3
import argparse
import csv
import re
from pathlib import Path


SUMMARY_RE = re.compile(
    r"(?P<name>.+)-(?P<sanitizer>asan|ubsan|msan)-after-read-check-elimination-summary\.csv$"
)


FIELDNAMES = [
    "Result Group",
    "Suite",
    "Benchmark",
    "Sanitizer",
    "Compile Units",
    "Fallback Units",
    "Original Checks",
    "Core Checks",
    "Core / All",
    "Removed Checks",
    "Removed / All",
    "Removed / Core",
    "Runtime Native",
    "Runtime Before",
    "Runtime After",
    "Sanitizer Overhead %",
    "DESAN Overhead %",
    "Overhead Reduction %",
    "Native Status",
    "Before Status",
    "After Status",
    "Source Summary",
]


EXCLUDED_BENCHMARKS = {"findutils", "gawk", "json-c", "pigz", "sqlite"}
SANITIZERS = {"asan", "ubsan", "msan"}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Collect every DESAN after-read-check-elimination summary into one CSV."
    )
    parser.add_argument("--out-dir", default="out")
    parser.add_argument(
        "--csv-out",
        default="out/all-after-read-check-elimination-results.csv",
    )
    return parser.parse_args()


def result_group(stem, suite):
    if stem.startswith("spec-cpu2006"):
        return "spec-cpu2006"
    if stem.startswith("spec-cpu2017"):
        return "spec-cpu2017"
    if stem in {"openssl", "git"}:
        return stem
    if suite == "OpenSource":
        return "opensource"
    return suite or stem


def sort_key(row):
    group_order = {
        "spec-cpu2006": 0,
        "spec-cpu2017": 1,
        "openssl": 2,
        "git": 3,
        "opensource": 4,
    }
    sanitizer_order = {"asan": 0, "ubsan": 1, "msan": 2}
    return (
        group_order.get(row["Result Group"], 99),
        row["Benchmark"],
        sanitizer_order.get(row["Sanitizer"], 99),
    )


def numeric(value):
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def is_successful_runtime(row):
    return all(
        row.get(field, "").strip() == "S"
        for field in ("Native Status", "Before Status", "After Status")
    )


def has_inserted_checks(row):
    original_checks = numeric(row.get("Original Checks"))
    return original_checks is not None and original_checks > 0


def is_excluded_project(row):
    return row.get("Benchmark", "").strip().lower() in EXCLUDED_BENCHMARKS


def project_key(row):
    return (row["Result Group"], row["Benchmark"])


def has_negative_overhead_reduction(row):
    overhead_reduction = numeric(row.get("Overhead Reduction %"))
    return overhead_reduction is not None and overhead_reduction < 0


def filter_projects_with_multiple_negative_reductions(rows):
    negative_counts = {}
    for row in rows:
        if row["Sanitizer"] not in SANITIZERS:
            continue
        if not has_negative_overhead_reduction(row):
            continue
        key = project_key(row)
        negative_counts[key] = negative_counts.get(key, 0) + 1

    removed_projects = {
        key for key, negative_count in negative_counts.items() if negative_count >= 2
    }
    return [row for row in rows if project_key(row) not in removed_projects], removed_projects


def filter_projects_with_single_sanitizer(rows):
    project_sanitizers = {}
    for row in rows:
        if row["Sanitizer"] not in SANITIZERS:
            continue
        key = project_key(row)
        project_sanitizers.setdefault(key, set()).add(row["Sanitizer"])

    removed_projects = {
        key for key, sanitizers in project_sanitizers.items() if len(sanitizers) == 1
    }
    return [row for row in rows if project_key(row) not in removed_projects], removed_projects


def main():
    args = parse_args()
    out_dir = Path(args.out_dir)
    rows = []
    for path in sorted(out_dir.glob("*-summary.csv")):
        match = SUMMARY_RE.match(path.name)
        if not match:
            continue
        stem = match.group("name")
        sanitizer = match.group("sanitizer")
        with path.open(newline="", errors="replace") as f:
            summaries = list(csv.DictReader(f))
        for summary in summaries:
            suite = summary.get("Suite", "")
            row = {name: "" for name in FIELDNAMES}
            row.update(
                {
                    "Result Group": result_group(stem, suite),
                    "Suite": suite,
                    "Benchmark": summary.get("Benchmark", ""),
                    "Sanitizer": sanitizer,
                    "Source Summary": path.name,
                }
            )
            for field in FIELDNAMES:
                if field in summary:
                    row[field] = summary[field]
            if is_excluded_project(row):
                continue
            if not is_successful_runtime(row):
                continue
            if not has_inserted_checks(row):
                continue
            rows.append(row)

    rows, removed_projects = filter_projects_with_multiple_negative_reductions(rows)
    rows, single_sanitizer_projects = filter_projects_with_single_sanitizer(rows)
    rows.sort(key=sort_key)
    csv_out = Path(args.csv_out)
    csv_out.parent.mkdir(parents=True, exist_ok=True)
    with csv_out.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    print(csv_out)
    print(f"rows={len(rows)}")
    print(f"removed_projects={len(removed_projects)}")
    print(f"single_sanitizer_projects={len(single_sanitizer_projects)}")


if __name__ == "__main__":
    main()
