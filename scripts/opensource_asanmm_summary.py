#!/usr/bin/env python3
import argparse
import csv
import statistics
from pathlib import Path


CORE_PREFIXES = (
    "__asan_report_load",
    "__asan_report_store",
    "__asan_load",
    "__asan_store",
)
READ_PREFIXES = ("__asan_report_load", "__asan_load")
WRITE_PREFIXES = ("__asan_report_store", "__asan_store")


def parse_args():
    parser = argparse.ArgumentParser(description="Aggregate ASAN-- open-source project results.")
    parser.add_argument("--suite", default="OpenSource")
    parser.add_argument("--benchmark", required=True)
    parser.add_argument("--base-records", required=True)
    parser.add_argument("--asanmm-records", required=True)
    parser.add_argument("--runtime-csv", required=True)
    parser.add_argument("--csv-out", default="")
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


def parse_check_log(path):
    total = 0
    counts = {}
    p = Path(path)
    if not p.exists():
        return total, counts

    current_type = None
    with p.open(errors="replace") as f:
        for line in f:
            line = line.strip()
            if line.startswith("Total Checks:"):
                try:
                    total = int(line.rsplit(" ", 1)[1])
                except ValueError:
                    total = 0
                continue
            if line.startswith("Check Type:"):
                current_type = line.split(":", 1)[1].strip()
                continue
            if line.startswith("Count:") and current_type:
                try:
                    counts[current_type] = counts.get(current_type, 0) + int(line.rsplit(" ", 1)[1])
                except ValueError:
                    pass
                current_type = None
    if total == 0:
        total = sum(counts.values())
    return total, counts


def sum_prefix(counts, prefixes):
    return sum(count for name, count in counts.items() if name.startswith(prefixes))


def parse_records(path, benchmark):
    row = {
        "compile_units": 0,
        "fallback_units": 0,
        "total_checks": 0,
        "core_checks": 0,
        "read_checks": 0,
        "write_checks": 0,
    }
    p = Path(path)
    if not p.exists():
        return row

    with p.open(newline="", errors="replace") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for rec in reader:
            rec_bench = rec.get("benchmark", "")
            if rec_bench not in (benchmark, "<unknown>"):
                continue
            row["compile_units"] += 1
            total, counts = parse_check_log(rec.get("pass_log", ""))
            if not counts and rec.get("status") != "direct-ir":
                row["fallback_units"] += 1
            row["total_checks"] += total
            row["core_checks"] += sum_prefix(counts, CORE_PREFIXES)
            row["read_checks"] += sum_prefix(counts, READ_PREFIXES)
            row["write_checks"] += sum_prefix(counts, WRITE_PREFIXES)
    return row


def parse_runtime_csv(path):
    runs = {}
    p = Path(path)
    if not p.exists():
        return runs
    with p.open(newline="", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            runs.setdefault(row.get("Variant", ""), []).append(
                (row.get("Status", ""), numeric(row.get("Seconds")))
            )
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


def overhead_metrics(native_status, base_status, asanmm_status, native_time, base_time, asanmm_time):
    sanitizer_overhead = None
    asanmm_overhead = None
    overhead_reduction = None
    runtime_reduction = None
    if (
        native_status == "S"
        and base_status == "S"
        and asanmm_status == "S"
        and native_time is not None
        and base_time is not None
        and asanmm_time is not None
        and native_time > 0
    ):
        sanitizer_overhead = (base_time - native_time) / native_time * 100.0
        asanmm_overhead = (asanmm_time - native_time) / native_time * 100.0
        if base_time != native_time:
            overhead_reduction = (base_time - asanmm_time) / (base_time - native_time) * 100.0
        if base_time > 0:
            runtime_reduction = (base_time - asanmm_time) / base_time * 100.0
    return sanitizer_overhead, asanmm_overhead, overhead_reduction, runtime_reduction


def pct(value):
    if value is None:
        return "--"
    return f"{value:.2f}%"


def num(value):
    return f"{int(value):,}"


def flt(value):
    if value is None:
        return "--"
    return f"{value:.3f}"


def main():
    args = parse_args()
    base = parse_records(args.base_records, args.benchmark)
    asanmm = parse_records(args.asanmm_records, args.benchmark)
    runtimes = parse_runtime_csv(args.runtime_csv)

    original = base["total_checks"]
    after = asanmm["total_checks"]
    removed = original - after if original or after else 0
    core_original = base["core_checks"]
    core_after = asanmm["core_checks"]
    read_removed = base["read_checks"] - asanmm["read_checks"]
    write_removed = base["write_checks"] - asanmm["write_checks"]

    native_time, native_status = summarize_runtime(runtimes, "native")
    base_time, base_status = summarize_runtime(runtimes, "asan-base")
    asanmm_time, asanmm_status = summarize_runtime(runtimes, "asanmm")
    sanitizer_overhead, asanmm_overhead, overhead_reduction, runtime_reduction = overhead_metrics(
        native_status, base_status, asanmm_status, native_time, base_time, asanmm_time
    )

    row = {
        "Suite": args.suite,
        "Benchmark": args.benchmark,
        "Compile Units Base": base["compile_units"],
        "Compile Units ASAN--": asanmm["compile_units"],
        "Fallback Units Base": base["fallback_units"],
        "Fallback Units ASAN--": asanmm["fallback_units"],
        "Original Checks": original,
        "ASAN-- Checks": after,
        "Removed Checks": removed,
        "Removed / Original": (removed / original * 100.0) if original else None,
        "Original Core Checks": core_original,
        "ASAN-- Core Checks": core_after,
        "Core / All Original": (core_original / original * 100.0) if original else None,
        "Removed Read Checks": read_removed,
        "Removed Store Checks": write_removed,
        "Runtime Native": native_time,
        "Runtime ASan": base_time,
        "Runtime ASAN--": asanmm_time,
        "Sanitizer Overhead %": sanitizer_overhead,
        "ASAN-- Overhead %": asanmm_overhead,
        "Overhead Reduction %": overhead_reduction,
        "Runtime Reduction vs ASan %": runtime_reduction,
        "Native Status": native_status,
        "ASan Status": base_status,
        "ASAN-- Status": asanmm_status,
    }

    if args.csv_out:
        with Path(args.csv_out).open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(row.keys()))
            writer.writeheader()
            writer.writerow(row)

    headers = [
        "Benchmark",
        "Original",
        "ASAN--",
        "Removed",
        "Removed/Orig",
        "Core/All",
        "Read Removed",
        "Store Removed",
        "Native(s)",
        "ASan(s)",
        "ASAN--(s)",
        "ASan Overhead",
        "ASAN-- Overhead",
        "Overhead Reduction",
        "Runtime Reduction",
        "Status",
    ]
    print("| " + " | ".join(headers) + " |")
    print("|" + "|".join(["---"] * len(headers)) + "|")
    print(
        "| "
        + " | ".join(
            [
                row["Benchmark"],
                num(row["Original Checks"]),
                num(row["ASAN-- Checks"]),
                num(row["Removed Checks"]),
                pct(row["Removed / Original"]),
                pct(row["Core / All Original"]),
                num(row["Removed Read Checks"]),
                num(row["Removed Store Checks"]),
                flt(row["Runtime Native"]),
                flt(row["Runtime ASan"]),
                flt(row["Runtime ASAN--"]),
                pct(row["Sanitizer Overhead %"]),
                pct(row["ASAN-- Overhead %"]),
                pct(row["Overhead Reduction %"]),
                pct(row["Runtime Reduction vs ASan %"]),
                f'{row["Native Status"]}->{row["ASan Status"]}->{row["ASAN-- Status"]}',
            ]
        )
        + " |"
    )


if __name__ == "__main__":
    main()
