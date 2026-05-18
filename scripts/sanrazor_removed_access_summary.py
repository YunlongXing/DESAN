#!/usr/bin/env python3
"""Classify SanRazor-disabled UBSan checks by READ/WRITE/UNKNOWN.

SanRazor's transformed bitcode often keeps the UBSan handler blocks in IR and
disables a check by replacing its guarding branch condition with a constant
true/false. This script scans the SanRazor .sr.bc files, finds those disabled
handler paths, and classifies only UBSan type_mismatch checks by LLVM's
TypeCheckKind:

  TypeCheckKind 0 => READ  (load)
  TypeCheckKind 1 => WRITE (store)
  everything else => UNKNOWN

For paper statistics, the removed-check count is the number of detected
disabled UBSan handler paths, not SanRazor's internal SC removed count. The
reported SanRazor count is kept as a reference column. The resulting WRITE
ratio is therefore a conservative UBSan memory-store ratio, not a guess over
arithmetic / pointer / bounds checks.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import subprocess
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


UBSAN_CALL_RE = re.compile(r"@(__ubsan_handle_[A-Za-z0-9_]+)")
BLOCK_RE = re.compile(r"^([A-Za-z$._-][\w$._-]*|\d+):\s*(?:;.*)?$")
CONST_BRANCH_RE = re.compile(
    r"\bbr\s+i1\s+(true|false),\s+label\s+%([A-Za-z$._-][\w$._-]*|\d+),"
    r"\s+label\s+%([A-Za-z$._-][\w$._-]*|\d+)"
)
GLOBAL_NAME_RE = re.compile(r"^(@[^\s=]+)\s*=")
I8_VALUE_RE = re.compile(r"\bi8\s+(\d+)\b")
TYPE_MISMATCH_CALL_DATA_RE = re.compile(
    r"@__ubsan_handle_type_mismatch_v1\("
    r".*?\*\s+(@[A-Za-z0-9_$.\-]+)\s+to\s+i8\*"
)


def run_llvm_dis(llvm_dis: str, bitcode: Path) -> str:
    proc = subprocess.run(
        [llvm_dis, "-o", "-", str(bitcode)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return proc.stdout


def parse_blocks(ir: str):
    blocks: dict[str, list[str]] = {}
    order: list[str] = []
    current: str | None = None
    for line in ir.splitlines():
        match = BLOCK_RE.match(line)
        if match:
            current = match.group(1)
            blocks[current] = []
            order.append(current)
            continue
        if current is not None:
            blocks[current].append(line)
    return blocks, order


def parse_type_mismatch_kinds(ir: str) -> dict[str, int]:
    kinds: dict[str, int] = {}
    for line in ir.splitlines():
        if "i8, i8" not in line:
            continue
        name = GLOBAL_NAME_RE.search(line)
        if not name:
            continue
        i8_values = I8_VALUE_RE.findall(line)
        if len(i8_values) < 2:
            continue
        # The last i8 in TypeMismatchData is TypeCheckKind. The preceding i8
        # is LogAlignment.
        kinds[name.group(1)] = int(i8_values[-1])
    return kinds


def classify_handler(call_line: str, type_kinds: dict[str, int]) -> tuple[str, str]:
    call_match = UBSAN_CALL_RE.search(call_line)
    if not call_match:
        return "UNKNOWN", ""

    callee = call_match.group(1)
    if callee == "__ubsan_handle_type_mismatch_v1":
        data_match = TYPE_MISMATCH_CALL_DATA_RE.search(call_line)
        kind = type_kinds.get(data_match.group(1)) if data_match else None
        if kind == 0:
            return "READ", callee
        if kind == 1:
            return "WRITE", callee
        return "UNKNOWN", callee

    return "UNKNOWN", callee


def first_ubsan_call(block_lines: list[str]) -> str | None:
    for line in block_lines:
        if UBSAN_CALL_RE.search(line):
            return line
    return None


def classify_file(llvm_dis: str, bitcode: Path, spec_root: Path, level: str) -> dict:
    ir = run_llvm_dis(llvm_dis, bitcode)
    blocks, order = parse_blocks(ir)
    type_kinds = parse_type_mismatch_kinds(ir)

    counts = Counter()
    callees = Counter()
    examples = []

    for label in order:
        for line in blocks[label]:
            br = CONST_BRANCH_RE.search(line)
            if not br or "!sanitycheck" not in line:
                continue
            const, true_succ, false_succ = br.groups()
            disabled_succ = false_succ if const == "true" else true_succ
            disabled_block = blocks.get(disabled_succ)
            if not disabled_block:
                continue
            call_line = first_ubsan_call(disabled_block)
            if not call_line:
                continue
            kind, callee = classify_handler(call_line, type_kinds)
            counts[kind] += 1
            if callee:
                callees[callee] += 1
            if len(examples) < 5:
                examples.append(
                    {
                        "block": label,
                        "disabled_block": disabled_succ,
                        "kind": kind,
                        "callee": callee,
                    }
                )

    bench = benchmark_from_path(bitcode, spec_root)
    return {
        "level": level,
        "benchmark": bench,
        "file": str(bitcode),
        "total": sum(counts.values()),
        "read": counts["READ"],
        "write": counts["WRITE"],
        "unknown": counts["UNKNOWN"],
        "callees": dict(callees),
        "examples": examples,
    }


def benchmark_from_path(path: Path, spec_root: Path) -> str:
    parts = path.relative_to(spec_root).parts
    try:
        idx = parts.index("CPU2006")
        return parts[idx + 1]
    except (ValueError, IndexError):
        return "unknown"


def find_sr_bitcode(spec_root: Path, level: str) -> list[Path]:
    pattern = (
        f"benchspec/CPU2006/*/run/build_peak_SR_ubsan_{level}.*/Cov/objects/*.sr.bc"
    )
    return sorted(spec_root.glob(pattern))


def read_summary_removed(summary_csv: Path | None) -> dict[str, int]:
    if not summary_csv or not summary_csv.exists():
        return {}
    out: dict[str, int] = {}
    with summary_csv.open(newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            bench = row.get("Benchmark", "")
            removed = row.get("Removed Checks", "0") or "0"
            try:
                out[bench] = int(float(removed))
            except ValueError:
                out[bench] = 0
    return out


def pct(num: int, den: int) -> float | None:
    if den == 0:
        return None
    return num * 100.0 / den


def fmt_pct(value: float | None) -> str:
    return "--" if value is None else f"{value:.2f}%"


def write_outputs(rows: list[dict], csv_out: Path | None, md_out: Path | None) -> None:
    fields = [
        "Level",
        "Benchmark",
        "SanRazor Reported Removed Checks",
        "Removed Checks",
        "Removed READ Checks",
        "Removed WRITE Checks",
        "Removed UNKNOWN Checks",
        "READ / Removed",
        "WRITE / Removed",
        "UNKNOWN / Removed",
        "Detected / Reported",
    ]
    if csv_out:
        csv_out.parent.mkdir(parents=True, exist_ok=True)
        with csv_out.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    if md_out:
        md_out.parent.mkdir(parents=True, exist_ok=True)
        with md_out.open("w") as f:
            f.write(
                "| Level | Benchmark | SanRazor Reported Removed | Removed | READ | WRITE | UNKNOWN | READ/Removed | WRITE/Removed | UNKNOWN/Removed | Detected/Reported |\n"
            )
            f.write("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|\n")
            for row in rows:
                f.write(
                    "| {Level} | {Benchmark} | {SanRazor Reported Removed Checks} | {Removed Checks} | "
                    "{Removed READ Checks} | {Removed WRITE Checks} | {Removed UNKNOWN Checks} | "
                    "{READ / Removed} | {WRITE / Removed} | {UNKNOWN / Removed} | {Detected / Reported} |\n".format(
                        **row
                    )
                )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec-root", required=True)
    parser.add_argument("--level", action="append", required=True)
    parser.add_argument("--llvm-dis", required=True)
    parser.add_argument("--summary-csv", action="append", default=[])
    parser.add_argument("--jobs", type=int, default=max(1, min(8, os.cpu_count() or 1)))
    parser.add_argument("--csv-out")
    parser.add_argument("--md-out")
    args = parser.parse_args()

    spec_root = Path(args.spec_root)
    summary_by_level: dict[str, dict[str, int]] = {}
    for path in args.summary_csv:
        p = Path(path)
        level_match = re.search(r"ubsan-(L\d+)-summary", p.name)
        if level_match:
            summary_by_level[level_match.group(1)] = read_summary_removed(p)

    aggregated: dict[tuple[str, str], Counter] = defaultdict(Counter)

    tasks = []
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for level in args.level:
            for bc in find_sr_bitcode(spec_root, level):
                tasks.append(
                    pool.submit(classify_file, args.llvm_dis, bc, spec_root, level)
                )
        for task in as_completed(tasks):
            result = task.result()
            key = (result["level"], result["benchmark"])
            aggregated[key]["detected"] += result["total"]
            aggregated[key]["read"] += result["read"]
            aggregated[key]["write"] += result["write"]
            aggregated[key]["unknown"] += result["unknown"]

    rows: list[dict] = []
    for level in args.level:
        level_total = Counter()
        benches = sorted(
            set(bench for lev, bench in aggregated if lev == level)
            | set(summary_by_level.get(level, {}))
        )
        for bench in benches:
            c = aggregated[(level, bench)]
            reported_removed = summary_by_level.get(level, {}).get(
                bench, c["detected"]
            )
            removed = c["detected"]
            row = {
                "Level": level,
                "Benchmark": bench,
                "SanRazor Reported Removed Checks": reported_removed,
                "Removed Checks": removed,
                "Removed READ Checks": c["read"],
                "Removed WRITE Checks": c["write"],
                "Removed UNKNOWN Checks": c["unknown"],
                "READ / Removed": fmt_pct(pct(c["read"], removed)),
                "WRITE / Removed": fmt_pct(pct(c["write"], removed)),
                "UNKNOWN / Removed": fmt_pct(pct(c["unknown"], removed)),
                "Detected / Reported": fmt_pct(pct(removed, reported_removed)),
            }
            rows.append(row)
            for k in ("detected", "read", "write", "unknown"):
                level_total[k] += c[k]
            level_total["reported_removed"] += reported_removed
            level_total["removed"] += removed

        if benches:
            c = level_total
            rows.append(
                {
                    "Level": level,
                    "Benchmark": "TOTAL",
                    "SanRazor Reported Removed Checks": c["reported_removed"],
                    "Removed Checks": c["removed"],
                    "Removed READ Checks": c["read"],
                    "Removed WRITE Checks": c["write"],
                    "Removed UNKNOWN Checks": c["unknown"],
                    "READ / Removed": fmt_pct(pct(c["read"], c["removed"])),
                    "WRITE / Removed": fmt_pct(pct(c["write"], c["removed"])),
                    "UNKNOWN / Removed": fmt_pct(pct(c["unknown"], c["removed"])),
                    "Detected / Reported": fmt_pct(
                        pct(c["removed"], c["reported_removed"])
                    ),
                }
            )

    write_outputs(rows, Path(args.csv_out) if args.csv_out else None, Path(args.md_out) if args.md_out else None)
    for row in rows:
        if row["Benchmark"] == "TOTAL":
            print(
                f'{row["Level"]}: reported={row["SanRazor Reported Removed Checks"]} '
                f'removed={row["Removed Checks"]} '
                f'read={row["Removed READ Checks"]}({row["READ / Removed"]}) '
                f'write={row["Removed WRITE Checks"]}({row["WRITE / Removed"]}) '
                f'unknown={row["Removed UNKNOWN Checks"]}({row["UNKNOWN / Removed"]}) '
                f'coverage={row["Detected / Reported"]}'
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
