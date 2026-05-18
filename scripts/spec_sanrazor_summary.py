#!/usr/bin/env python3
import argparse
import csv
import glob
import re
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(description="Aggregate SanRazor SPEC results.")
    parser.add_argument("--suite", default="CPU2006")
    parser.add_argument("--level", default="L2")
    parser.add_argument("--check-glob", action="append", default=[])
    parser.add_argument("--native-csv", action="append", default=[])
    parser.add_argument("--base-csv", action="append", default=[])
    parser.add_argument("--sanrazor-csv", action="append", default=[])
    parser.add_argument("--csv-out", default="")
    return parser.parse_args()


def normalize_benchmark_name(name):
    return re.sub(r"\s*\((base|peak)\)\s*$", "", (name or "").strip())


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
            if p.suffix == ".rsf":
                results.update(parse_runtime_rsf(p))
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


def parse_runtime_rsf(path):
    raw = {}
    pattern = re.compile(r"^spec\.cpu2006\.results\.([^.]+)\.(base|peak)\.(\d+)\.([^:]+):\s*(.*)$")
    with Path(path).open(errors="replace") as f:
        for line in f:
            match = pattern.match(line.rstrip("\n"))
            if not match:
                continue
            key = ".".join(match.group(i) for i in (1, 2, 3))
            field = match.group(4)
            value = match.group(5).strip()
            raw.setdefault(key, {})[field] = value

    results = {}
    for row in raw.values():
        bench = normalize_benchmark_name(row.get("benchmark", ""))
        if not re.match(r"^\d{3}\.", bench):
            continue
        run_time = numeric(row.get("reported_time"))
        status = row.get("valid", "NR").strip() or "NR"
        selected = row.get("selected", "").strip()
        old = results.get(bench)
        if old is None or (old["time"] is None and run_time is not None) or selected == "1":
            results[bench] = {"time": run_time, "status": status}
    return results


def benchmark_from_check_path(path):
    for part in Path(path).parts:
        if re.match(r"^\d{3}\.", part):
            return part
    return None


def parse_check_file(path):
    p = Path(path)
    totals = {}
    if not p.exists():
        return totals

    seen = set()
    with p.open(errors="replace") as f:
        for line_no, line in enumerate(f):
            if line_no % 2 != 0:
                continue
            parts = line.split()
            if len(parts) < 9:
                continue
            try:
                original = int(parts[1])
                remaining = int(parts[3])
                original_cost = int(parts[7])
                remaining_cost = int(parts[8])
            except ValueError:
                continue
            key = tuple(parts[:9])
            if key in seen:
                continue
            seen.add(key)
            row = totals.setdefault(
                "counts",
                {"original": 0, "remaining": 0, "original_cost": 0, "remaining_cost": 0},
            )
            row["original"] += original
            row["remaining"] += remaining
            row["original_cost"] += original_cost
            row["remaining_cost"] += remaining_cost
    return totals.get("counts", {"original": 0, "remaining": 0, "original_cost": 0, "remaining_cost": 0})


def parse_checks(globs):
    checks = {}
    for pattern in globs:
        for path in glob.glob(str(Path(pattern).expanduser())):
            bench = benchmark_from_check_path(path)
            if not bench:
                continue
            counts = parse_check_file(path)
            row = checks.setdefault(
                bench,
                {"original": 0, "remaining": 0, "original_cost": 0, "remaining_cost": 0},
            )
            for key in row:
                row[key] += counts.get(key, 0)
    return checks


def overhead_metrics(native_status, base_status, sanrazor_status, native_time, base_time, sanrazor_time):
    sanitizer_overhead = None
    sanrazor_overhead = None
    overhead_reduction = None
    runtime_reduction = None
    if (
        native_status == "S"
        and base_status == "S"
        and sanrazor_status == "S"
        and native_time is not None
        and base_time is not None
        and sanrazor_time is not None
        and native_time > 0
    ):
        sanitizer_overhead = (base_time - native_time) / native_time * 100.0
        sanrazor_overhead = (sanrazor_time - native_time) / native_time * 100.0
        if base_time != native_time:
            overhead_reduction = (base_time - sanrazor_time) / (base_time - native_time) * 100.0
        if base_time > 0:
            runtime_reduction = (base_time - sanrazor_time) / base_time * 100.0
    return sanitizer_overhead, sanrazor_overhead, overhead_reduction, runtime_reduction


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


def main():
    args = parse_args()
    checks = parse_checks(args.check_glob)
    native = parse_runtime_csv(args.native_csv)
    base = parse_runtime_csv(args.base_csv)
    sanrazor = parse_runtime_csv(args.sanrazor_csv)
    benches = sorted(set(checks) | set(native) | set(base) | set(sanrazor))

    rows = []
    for bench in benches:
        c = checks.get(bench, {"original": 0, "remaining": 0, "original_cost": 0, "remaining_cost": 0})
        original = c["original"]
        remaining = c["remaining"]
        removed = max(0, original - remaining)
        original_cost = c["original_cost"]
        remaining_cost = c["remaining_cost"]
        removed_cost = max(0, original_cost - remaining_cost)

        native_time = native.get(bench, {}).get("time")
        base_time = base.get(bench, {}).get("time")
        sanrazor_time = sanrazor.get(bench, {}).get("time")
        native_status = native.get(bench, {}).get("status", "NR")
        base_status = base.get(bench, {}).get("status", "NR")
        sanrazor_status = sanrazor.get(bench, {}).get("status", "NR")
        sanitizer_overhead, sanrazor_overhead, overhead_reduction, runtime_reduction = overhead_metrics(
            native_status, base_status, sanrazor_status, native_time, base_time, sanrazor_time
        )

        rows.append(
            {
                "Suite": args.suite,
                "Benchmark": bench,
                "SanRazor Level": args.level,
                "Original Checks": original,
                "SanRazor Checks": remaining,
                "Removed Checks": removed,
                "Removed / Original": (removed / original * 100.0) if original else None,
                "Original Check Cost": original_cost,
                "SanRazor Check Cost": remaining_cost,
                "Removed Check Cost": removed_cost,
                "Check Cost Reduction %": (removed_cost / original_cost * 100.0) if original_cost else None,
                "Runtime Native": native_time,
                "Runtime UBSan": base_time,
                "Runtime SanRazor": sanrazor_time,
                "Sanitizer Overhead %": sanitizer_overhead,
                "SanRazor Overhead %": sanrazor_overhead,
                "Overhead Reduction %": overhead_reduction,
                "Runtime Reduction vs UBSan %": runtime_reduction,
                "Native Status": native_status,
                "UBSan Status": base_status,
                "SanRazor Status": sanrazor_status,
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
        "SanRazor",
        "Removed",
        "Removed/Orig",
        "Cost Reduction",
        "Native(s)",
        "UBSan(s)",
        "SanRazor(s)",
        "UBSan Overhead",
        "SanRazor Overhead",
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
                    fmt_int(row["Original Checks"]),
                    fmt_int(row["SanRazor Checks"]),
                    fmt_int(row["Removed Checks"]),
                    fmt_pct(row["Removed / Original"]),
                    fmt_pct(row["Check Cost Reduction %"]),
                    fmt_float(row["Runtime Native"]),
                    fmt_float(row["Runtime UBSan"]),
                    fmt_float(row["Runtime SanRazor"]),
                    fmt_pct(row["Sanitizer Overhead %"]),
                    fmt_pct(row["SanRazor Overhead %"]),
                    fmt_pct(row["Overhead Reduction %"]),
                    fmt_pct(row["Runtime Reduction vs UBSan %"]),
                    f'{row["Native Status"]}->{row["UBSan Status"]}->{row["SanRazor Status"]}',
                ]
            )
            + " |"
        )


if __name__ == "__main__":
    main()
