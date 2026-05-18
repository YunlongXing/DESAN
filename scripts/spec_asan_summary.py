#!/usr/bin/env python3
import argparse
import csv
import glob
import re
from pathlib import Path


DEFAULT_CORE_PREFIXES = (
    "__asan_report_load",
    "__asan_report_store",
    "__asan_load",
    "__asan_store",
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Aggregate DESAN sanitizer SPEC results per benchmark."
    )
    parser.add_argument("--records", action="append", default=[], help="compile_records.tsv")
    parser.add_argument("--native-csv", action="append", default=[], help="uninstrumented/native SPEC CSV")
    parser.add_argument("--before-csv", action="append", default=[], help="ASan baseline SPEC CSV")
    parser.add_argument("--after-csv", action="append", default=[], help="DESAN SPEC CSV")
    parser.add_argument("--suite", default="", help="suite label")
    parser.add_argument("--csv-out", default="", help="optional CSV output")
    parser.add_argument(
        "--core-prefix",
        action="append",
        default=[],
        help="check name prefix counted as core; defaults to ASan load/store core checks",
    )
    return parser.parse_args()


def numeric(value):
    if value is None:
        return None
    value = value.strip()
    if not value or value == "--":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def parse_runtime_csv(paths):
    results = {}
    for path in paths:
        expanded = glob.glob(str(Path(path).expanduser()))
        if not expanded:
            expanded = [path]
        for expanded_path in expanded:
            p = Path(expanded_path).expanduser()
            if not p.exists():
                continue
            with p.open(newline="", errors="replace") as f:
                reader = csv.reader(f)
                header = None
                for row in reader:
                    if not row:
                        continue
                    if row[0] == "Benchmark":
                        header = {name: i for i, name in enumerate(row)}
                        continue
                    if header is None or row[0].startswith('"'):
                        continue
                    bench = row[0].strip()
                    if not re.match(r"^\d{3}\.", bench):
                        continue
                    time_idx = header.get("Est. Base Run Time")
                    status_idx = header.get("Base Status")
                    selected_idx = header.get("Base Selected")
                    run_time = numeric(row[time_idx]) if time_idx is not None and time_idx < len(row) else None
                    status = row[status_idx].strip() if status_idx is not None and status_idx < len(row) else ""
                    selected = row[selected_idx].strip() if selected_idx is not None and selected_idx < len(row) else ""
                    old = results.get(bench)
                    if old is None or (old["time"] is None and run_time is not None) or selected == "1":
                        results[bench] = {"time": run_time, "status": status or "NR"}
    return results


def parse_pass_log(path, core_prefixes):
    total = 0
    core = 0
    removed = 0
    p = Path(path)
    if not p.exists():
        return total, core, removed

    current_type = None
    saw_total = False
    with p.open(errors="replace") as f:
        for line in f:
            line = line.strip()
            if line.startswith("Total Checks:") and not saw_total:
                try:
                    total = int(line.rsplit(" ", 1)[1])
                except ValueError:
                    total = 0
                saw_total = True
                continue
            if line.startswith("Check Type:"):
                current_type = line.split(":", 1)[1].strip()
                continue
            if line.startswith("Count:") and current_type:
                try:
                    count = int(line.rsplit(" ", 1)[1])
                except ValueError:
                    count = 0
                if current_type.startswith(core_prefixes):
                    core += count
                current_type = None
                continue
            if line.startswith("DESAN Removed Redundant Checks:") or line.startswith("DESAN Removed Redundant READ Checks:"):
                try:
                    removed = int(line.rsplit(" ", 1)[1])
                except ValueError:
                    removed = 0
    return total, core, removed


def parse_records(paths, core_prefixes):
    rows = {}
    for path in paths:
        p = Path(path).expanduser()
        if not p.exists():
            continue
        with p.open(newline="", errors="replace") as f:
            reader = csv.DictReader(f, delimiter="\t")
            for rec in reader:
                if rec.get("status") == "status" or rec.get("benchmark") == "benchmark":
                    continue
                bench = rec.get("benchmark", "<unknown>") or "<unknown>"
                row = rows.setdefault(
                    bench,
                    {
                        "benchmark": bench,
                        "compile_units": 0,
                        "fallback_units": 0,
                        "total_checks": 0,
                        "core_checks": 0,
                        "removed_checks": 0,
                    },
                )
                row["compile_units"] += 1
                status = rec.get("status")
                if status == "pass":
                    total, core, removed = parse_pass_log(
                        rec.get("pass_log", ""), core_prefixes
                    )
                    row["total_checks"] += total
                    row["core_checks"] += core
                    row["removed_checks"] += removed
                    continue
                if status == "pass-fallback":
                    row["fallback_units"] += 1
                    total, core, _ = parse_pass_log(
                        rec.get("pass_log", ""), core_prefixes
                    )
                    row["total_checks"] += total
                    row["core_checks"] += core
                    continue
                row["fallback_units"] += 1
    return rows


def fmt_int(value):
    return f"{int(value):,}"


def fmt_float(value):
    if value is None:
        return "--"
    return f"{value:.3f}"


def fmt_pct(value):
    if value is None:
        return "--"
    return f"{value:.2f}%"


def compute_overhead_metrics(native_status, before_status, after_status, native_time, before_time, after_time):
    sanitizer_overhead = None
    desan_overhead = None
    overhead_reduction = None
    if (
        native_status == "S"
        and before_status == "S"
        and after_status == "S"
        and native_time is not None
        and before_time is not None
        and after_time is not None
        and native_time > 0
    ):
        sanitizer_overhead = (before_time - native_time) / native_time * 100.0
        desan_overhead = (after_time - native_time) / native_time * 100.0
        if before_time != native_time:
            overhead_reduction = (before_time - after_time) / (before_time - native_time) * 100.0
    return sanitizer_overhead, desan_overhead, overhead_reduction


def main():
    args = parse_args()
    core_prefixes = tuple(args.core_prefix) if args.core_prefix else DEFAULT_CORE_PREFIXES
    counts = parse_records(args.records, core_prefixes)
    native = parse_runtime_csv(args.native_csv)
    before = parse_runtime_csv(args.before_csv)
    after = parse_runtime_csv(args.after_csv)
    have_native = bool(args.native_csv)
    benches = sorted(set(counts) | set(native) | set(before) | set(after))

    out_rows = []
    for bench in benches:
        c = counts.get(
            bench,
            {
                "compile_units": 0,
                "fallback_units": 0,
                "total_checks": 0,
                "core_checks": 0,
                "removed_checks": 0,
            },
        )
        native_time = native.get(bench, {}).get("time")
        before_time = before.get(bench, {}).get("time")
        after_time = after.get(bench, {}).get("time")
        native_status = native.get(bench, {}).get("status", "NR")
        before_status = before.get(bench, {}).get("status", "NR")
        after_status = after.get(bench, {}).get("status", "NR")
        if (
            c["compile_units"] == 0
            and native_status == "NR"
            and before_status == "NR"
            and after_status == "NR"
        ):
            continue
        sanitizer_overhead, desan_overhead, overhead_reduction = compute_overhead_metrics(
            native_status, before_status, after_status, native_time, before_time, after_time
        )

        total_checks = c["total_checks"]
        core_checks = c["core_checks"]
        removed = c["removed_checks"]
        core_ratio = (core_checks / total_checks * 100.0) if total_checks else None
        removal_ratio = (removed / total_checks * 100.0) if total_checks else None
        core_removal_ratio = (removed / core_checks * 100.0) if core_checks else None

        out_rows.append(
            {
                "Suite": args.suite,
                "Benchmark": bench,
                "Compile Units": c["compile_units"],
                "Fallback Units": c["fallback_units"],
                "Original Checks": total_checks,
                "Core Checks": core_checks,
                "Core / All": core_ratio,
                "Removed Checks": removed,
                "Removed / All": removal_ratio,
                "Removed / Core": core_removal_ratio,
                "Runtime Native": native_time,
                "Runtime Before": before_time,
                "Runtime After": after_time,
                "Sanitizer Overhead %": sanitizer_overhead,
                "DESAN Overhead %": desan_overhead,
                "Overhead Reduction %": overhead_reduction,
                "Native Status": native_status,
                "Before Status": before_status,
                "After Status": after_status,
            }
        )

    if args.csv_out:
        with Path(args.csv_out).open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()) if out_rows else [])
            if out_rows:
                writer.writeheader()
                writer.writerows(out_rows)

    headers = [
        "Benchmark",
        "Orig Checks",
        "Core",
        "Core/All",
        "Removed",
        "Removed/All",
        "Removed/Core",
        "Native(s)",
        "Before(s)",
        "After(s)",
        "Sanitizer Overhead",
        "DESAN Overhead",
        "Overhead Reduction",
        "Status",
    ]
    print("| " + " | ".join(headers) + " |")
    print("|" + "|".join(["---"] * len(headers)) + "|")
    for row in out_rows:
        print(
            "| "
            + " | ".join(
                [
                    row["Benchmark"],
                    fmt_int(row["Original Checks"]),
                    fmt_int(row["Core Checks"]),
                    fmt_pct(row["Core / All"]),
                    fmt_int(row["Removed Checks"]),
                    fmt_pct(row["Removed / All"]),
                    fmt_pct(row["Removed / Core"]),
                    fmt_float(row["Runtime Native"]),
                    fmt_float(row["Runtime Before"]),
                    fmt_float(row["Runtime After"]),
                    fmt_pct(row["Sanitizer Overhead %"]),
                    fmt_pct(row["DESAN Overhead %"]),
                    fmt_pct(row["Overhead Reduction %"]),
                    f'{row["Native Status"]}->{row["Before Status"]}->{row["After Status"]}',
                ]
            )
            + " |"
        )


if __name__ == "__main__":
    main()
