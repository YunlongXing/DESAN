#!/usr/bin/env python3
import argparse
import csv
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(
        description="Collect per-project DESAN open-source batch summaries."
    )
    parser.add_argument("--out-dir", default="/home/dragon/DESAN/out")
    parser.add_argument("--projects", default="")
    parser.add_argument("--sanitizers", default="asan,ubsan,msan")
    parser.add_argument(
        "--csv-out",
        default="/home/dragon/DESAN/out/oss-after-read-check-elimination-results.csv",
    )
    parser.add_argument(
        "--md-out",
        default="/home/dragon/DESAN/out/oss-after-read-check-elimination-results.md",
    )
    return parser.parse_args()


def read_statuses(path):
    statuses = {}
    if not path.exists():
        return statuses
    with path.open(newline="", errors="replace") as f:
        for row in csv.DictReader(f):
            key = (row.get("Project", ""), row.get("Sanitizer", ""))
            statuses[key] = (row.get("Status", ""), row.get("Message", ""))
    return statuses


def fmt_int(value):
    try:
        return f"{int(float(value)):,}"
    except (TypeError, ValueError):
        return "--"


def fmt_float(value):
    try:
        return f"{float(value):.3f}"
    except (TypeError, ValueError):
        return "--"


def fmt_pct(value):
    try:
        return f"{float(value):.2f}%"
    except (TypeError, ValueError):
        return "--"


def read_summary(path):
    if not path.exists():
        return None
    with path.open(newline="", errors="replace") as f:
        rows = list(csv.DictReader(f))
    return rows[0] if rows else None


def main():
    args = parse_args()
    out_dir = Path(args.out_dir)
    sanitizers = [s.strip() for s in args.sanitizers.split(",") if s.strip()]
    if args.projects:
        projects = [p.strip() for p in args.projects.split(",") if p.strip()]
    else:
        projects = sorted(
            {
                p.name.split("-")[0]
                for p in out_dir.glob("*-after-read-check-elimination-summary.csv")
            }
        )
    statuses = read_statuses(out_dir / "oss-batch-after-read-check-elimination-status.csv")

    fieldnames = [
        "Project",
        "Sanitizer",
        "Status",
        "Message",
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
    ]
    rows = []
    for project in projects:
        for sanitizer in sanitizers:
            status, message = statuses.get((project, sanitizer), ("", ""))
            summary = read_summary(
                out_dir
                / f"{project}-{sanitizer}-after-read-check-elimination-summary.csv"
            )
            row = {name: "" for name in fieldnames}
            row.update({"Project": project, "Sanitizer": sanitizer, "Status": status, "Message": message})
            if summary:
                row.update(
                    {
                        "Original Checks": summary.get("Original Checks", ""),
                        "Core Checks": summary.get("Core Checks", ""),
                        "Core / All": summary.get("Core / All", ""),
                        "Removed Checks": summary.get("Removed Checks", ""),
                        "Removed / All": summary.get("Removed / All", ""),
                        "Removed / Core": summary.get("Removed / Core", ""),
                        "Runtime Native": summary.get("Runtime Native", ""),
                        "Runtime Before": summary.get("Runtime Before", ""),
                        "Runtime After": summary.get("Runtime After", ""),
                        "Sanitizer Overhead %": summary.get("Sanitizer Overhead %", ""),
                        "DESAN Overhead %": summary.get("DESAN Overhead %", ""),
                        "Overhead Reduction %": summary.get("Overhead Reduction %", ""),
                    }
                )
            rows.append(row)

    csv_out = Path(args.csv_out)
    csv_out.parent.mkdir(parents=True, exist_ok=True)
    with csv_out.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    md_out = Path(args.md_out)
    with md_out.open("w") as f:
        f.write(
            "| Project | Sanitizer | Status | Orig Checks | Core/All | Removed | Removed/All | Native(s) | Before(s) | After(s) | Sanitizer Overhead | DESAN Overhead | Overhead Reduction |\n"
        )
        f.write("|---|---|---|---|---|---|---|---|---|---|---|---|---|\n")
        for row in rows:
            f.write(
                "| "
                + " | ".join(
                    [
                        row["Project"],
                        row["Sanitizer"],
                        row["Status"] or "--",
                        fmt_int(row["Original Checks"]),
                        fmt_pct(row["Core / All"]),
                        fmt_int(row["Removed Checks"]),
                        fmt_pct(row["Removed / All"]),
                        fmt_float(row["Runtime Native"]),
                        fmt_float(row["Runtime Before"]),
                        fmt_float(row["Runtime After"]),
                        fmt_pct(row["Sanitizer Overhead %"]),
                        fmt_pct(row["DESAN Overhead %"]),
                        fmt_pct(row["Overhead Reduction %"]),
                    ]
                )
                + " |\n"
            )
    print(csv_out)
    print(md_out)


if __name__ == "__main__":
    main()
