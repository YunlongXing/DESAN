#!/usr/bin/env python3
import argparse
import csv
import statistics
from pathlib import Path


DEFAULT_CORE_PREFIXES = (
    "__asan_report_load",
    "__asan_report_store",
    "__asan_load",
    "__asan_store",
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Aggregate DESAN sanitizer results for an open-source project."
    )
    parser.add_argument("--suite", default="opensource")
    parser.add_argument("--benchmark", required=True)
    parser.add_argument("--records", required=True)
    parser.add_argument("--runtime-csv", required=True)
    parser.add_argument("--csv-out", default="")
    parser.add_argument("--core-prefix", action="append", default=[])
    parser.add_argument("--before-variant", default="asan-base")
    parser.add_argument("--after-variant", default="desan")
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
                total = int(line.rsplit(" ", 1)[1])
                saw_total = True
                continue
            if line.startswith("Check Type:"):
                current_type = line.split(":", 1)[1].strip()
                continue
            if line.startswith("Count:") and current_type:
                count = int(line.rsplit(" ", 1)[1])
                if current_type.startswith(core_prefixes):
                    core += count
                current_type = None
                continue
            if (
                line.startswith("DESAN Removed Redundant Checks:")
                or line.startswith("DESAN Removed Redundant READ Checks:")
            ):
                removed = int(line.rsplit(" ", 1)[1])
    return total, core, removed


def parse_records(path, benchmark, core_prefixes):
    result = {
        "compile_units": 0,
        "fallback_units": 0,
        "total_checks": 0,
        "core_checks": 0,
        "removed_checks": 0,
    }
    p = Path(path)
    if not p.exists():
        return result
    with p.open(newline="", errors="replace") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for rec in reader:
            if rec.get("benchmark") not in (benchmark, "<unknown>"):
                continue
            result["compile_units"] += 1
            status = rec.get("status")
            if status == "pass":
                total, core, removed = parse_pass_log(rec.get("pass_log", ""), core_prefixes)
                result["total_checks"] += total
                result["core_checks"] += core
                result["removed_checks"] += removed
                continue
            if status == "pass-fallback":
                result["fallback_units"] += 1
                total, core, _ = parse_pass_log(rec.get("pass_log", ""), core_prefixes)
                result["total_checks"] += total
                result["core_checks"] += core
                continue
            result["fallback_units"] += 1
    return result


def parse_runtime_csv(path):
    runs = {}
    p = Path(path)
    if not p.exists():
        return runs
    with p.open(newline="", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            variant = row.get("Variant", "")
            status = row.get("Status", "")
            seconds = numeric(row.get("Seconds"))
            runs.setdefault(variant, []).append((status, seconds))
    return runs


def summarize_runtime(runs, variant):
    values = [
        seconds
        for status, seconds in runs.get(variant, [])
        if status == "S" and seconds is not None
    ]
    if not values:
        return None, "NR"
    return statistics.mean(values), "S"


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
    counts = parse_records(args.records, args.benchmark, core_prefixes)
    runtimes = parse_runtime_csv(args.runtime_csv)

    native_time, native_status = summarize_runtime(runtimes, "native")
    before_time, before_status = summarize_runtime(runtimes, args.before_variant)
    after_time, after_status = summarize_runtime(runtimes, args.after_variant)

    total = counts["total_checks"]
    core = counts["core_checks"]
    removed = counts["removed_checks"]
    core_ratio = (core / total * 100.0) if total else None
    removed_ratio = (removed / total * 100.0) if total else None
    removed_core_ratio = (removed / core * 100.0) if core else None

    sanitizer_overhead, desan_overhead, overhead_reduction = compute_overhead_metrics(
        native_status, before_status, after_status, native_time, before_time, after_time
    )

    row = {
        "Suite": args.suite,
        "Benchmark": args.benchmark,
        "Compile Units": counts["compile_units"],
        "Fallback Units": counts["fallback_units"],
        "Original Checks": total,
        "Core Checks": core,
        "Core / All": core_ratio,
        "Removed Checks": removed,
        "Removed / All": removed_ratio,
        "Removed / Core": removed_core_ratio,
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

    if args.csv_out:
        with Path(args.csv_out).open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(row.keys()))
            writer.writeheader()
            writer.writerow(row)

    print("| Benchmark | Orig Checks | Core | Core/All | Removed | Removed/All | Removed/Core | Native(s) | Before(s) | After(s) | Sanitizer Overhead | DESAN Overhead | Overhead Reduction | Status |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    print(
        "| "
        + " | ".join(
            [
                args.benchmark,
                fmt_int(total),
                fmt_int(core),
                fmt_pct(core_ratio),
                fmt_int(removed),
                fmt_pct(removed_ratio),
                fmt_pct(removed_core_ratio),
                fmt_float(native_time),
                fmt_float(before_time),
                fmt_float(after_time),
                fmt_pct(sanitizer_overhead),
                fmt_pct(desan_overhead),
                fmt_pct(overhead_reduction),
                f"{native_status}->{before_status}->{after_status}",
            ]
        )
        + " |"
    )


if __name__ == "__main__":
    main()
