#!/usr/bin/env python3
import argparse
import csv
import glob
import re
from pathlib import Path


CORE_PREFIXES = (
    "__asan_report_load",
    "__asan_report_store",
    "__asan_load",
    "__asan_store",
)
READ_PREFIXES = ("__asan_report_load", "__asan_load")
WRITE_PREFIXES = ("__asan_report_store", "__asan_store")


def normalize_benchmark_name(name):
    return re.sub(r"\s*\((base|peak)\)\s*$", "", (name or "").strip())


def parse_args():
    parser = argparse.ArgumentParser(description="Aggregate ASAN-- SPEC results.")
    parser.add_argument("--base-records", action="append", default=[], help="vanilla ASan compile_records.tsv")
    parser.add_argument("--asanmm-records", action="append", default=[], help="ASAN-- compile_records.tsv")
    parser.add_argument("--native-csv", action="append", default=[], help="native SPEC CSV")
    parser.add_argument("--base-csv", action="append", default=[], help="vanilla ASan SPEC CSV")
    parser.add_argument("--asanmm-csv", action="append", default=[], help="ASAN-- SPEC CSV")
    parser.add_argument("--suite", default="", help="suite label")
    parser.add_argument("--csv-out", default="", help="optional CSV output")
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
        expanded = glob.glob(str(Path(path).expanduser())) or [path]
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
                    bench = normalize_benchmark_name(row[0])
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


def parse_records(paths):
    rows = {}
    for path in paths:
        p = Path(path).expanduser()
        if not p.exists():
            continue
        with p.open(newline="", errors="replace") as f:
            reader = csv.DictReader(f, delimiter="\t")
            for rec in reader:
                bench = normalize_benchmark_name(rec.get("benchmark", "<unknown>") or "<unknown>")
                if bench == "benchmark" or rec.get("status") == "status":
                    continue
                row = rows.setdefault(
                    bench,
                    {
                        "compile_units": 0,
                        "fallback_units": 0,
                        "total_checks": 0,
                        "core_checks": 0,
                        "read_checks": 0,
                        "write_checks": 0,
                    },
                )
                row["compile_units"] += 1
                total, counts = parse_check_log(rec.get("pass_log", ""))
                if not counts and rec.get("status") != "direct-ir":
                    row["fallback_units"] += 1
                row["total_checks"] += total
                row["core_checks"] += sum_prefix(counts, CORE_PREFIXES)
                row["read_checks"] += sum_prefix(counts, READ_PREFIXES)
                row["write_checks"] += sum_prefix(counts, WRITE_PREFIXES)
    return rows


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


def main():
    args = parse_args()
    base_counts = parse_records(args.base_records)
    asanmm_counts = parse_records(args.asanmm_records)
    native = parse_runtime_csv(args.native_csv)
    base = parse_runtime_csv(args.base_csv)
    asanmm = parse_runtime_csv(args.asanmm_csv)
    benches = sorted(set(base_counts) | set(asanmm_counts) | set(native) | set(base) | set(asanmm))

    rows = []
    for bench in benches:
        b = base_counts.get(bench, {})
        a = asanmm_counts.get(bench, {})
        original = b.get("total_checks", 0)
        after = a.get("total_checks", 0)
        removed = original - after if original or after else 0
        core_original = b.get("core_checks", 0)
        core_after = a.get("core_checks", 0)
        read_removed = b.get("read_checks", 0) - a.get("read_checks", 0)
        write_removed = b.get("write_checks", 0) - a.get("write_checks", 0)
        native_time = native.get(bench, {}).get("time")
        base_time = base.get(bench, {}).get("time")
        asanmm_time = asanmm.get(bench, {}).get("time")
        native_status = native.get(bench, {}).get("status", "NR")
        base_status = base.get(bench, {}).get("status", "NR")
        asanmm_status = asanmm.get(bench, {}).get("status", "NR")
        sanitizer_overhead, asanmm_overhead, overhead_reduction, runtime_reduction = overhead_metrics(
            native_status, base_status, asanmm_status, native_time, base_time, asanmm_time
        )
        rows.append(
            {
                "Suite": args.suite,
                "Benchmark": bench,
                "Compile Units Base": b.get("compile_units", 0),
                "Compile Units ASAN--": a.get("compile_units", 0),
                "Fallback Units Base": b.get("fallback_units", 0),
                "Fallback Units ASAN--": a.get("fallback_units", 0),
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
        )

    if args.csv_out and rows:
        with Path(args.csv_out).open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

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
    for row in rows:
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
