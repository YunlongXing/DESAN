#!/usr/bin/env python3
import argparse
import collections
import re
from pathlib import Path


CORE_PREFIXES = {
    "asan": (
        "__asan_report_load",
        "__asan_report_store",
        "__asan_load",
        "__asan_store",
    ),
    "ubsan": (
        "__ubsan_handle_type_mismatch_v1",
        "__ubsan_handle_pointer_overflow",
        "__ubsan_handle_out_of_bounds",
        "__ubsan_handle_shift_out_of_bounds",
    ),
    "msan": (
        "__msan_warning",
        "__msan_param_",
        "__msan_retval_",
        "__msan_va_arg_",
    ),
}

CALL_RE = re.compile(r"\b(?:call|invoke)\b[^@]*@([A-Za-z_][A-Za-z0-9_.$]*)")


def parse_args():
    parser = argparse.ArgumentParser(description="Count sanitizer call sites in LLVM IR.")
    parser.add_argument("--sanitizer", default="asan", help="asan, ubsan, or msan")
    parser.add_argument("ir", help="LLVM IR file")
    return parser.parse_args()


def sanitizer_prefix(kind):
    kind = kind.lower()
    if kind in ("asan", "address"):
        return "__asan_"
    if kind in ("ubsan", "undefined"):
        return "__ubsan_"
    if kind in ("msan", "memory"):
        return "__msan_"
    return "__"


def sanitizer_label(kind):
    kind = kind.lower()
    if kind in ("asan", "address"):
        return "ASan"
    if kind in ("ubsan", "undefined"):
        return "UBSan"
    if kind in ("msan", "memory"):
        return "MemSan"
    return kind


def normalize_kind(kind):
    kind = kind.lower()
    if kind == "address":
        return "asan"
    if kind == "undefined":
        return "ubsan"
    if kind == "memory":
        return "msan"
    return kind


def main():
    args = parse_args()
    kind = normalize_kind(args.sanitizer)
    prefix = sanitizer_prefix(kind)
    counts = collections.Counter()
    path = Path(args.ir)

    with path.open(errors="replace") as f:
        for line in f:
            match = CALL_RE.search(line)
            if not match:
                continue
            name = match.group(1)
            if name.startswith(prefix):
                counts[name] += 1

    total = sum(counts.values())
    core_prefixes = CORE_PREFIXES.get(kind, ())
    core = sum(count for name, count in counts.items() if name.startswith(core_prefixes))

    print("DESAN Sanitizer Check Count Summary")
    print(f"Input: {path}")
    print(f"Total Checks: {total}")
    print(f"Core Checks: {core}")
    print(f"Sanitizer: {sanitizer_label(kind)}")
    for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        ratio = (count / total * 100.0) if total else 0.0
        print(f"Check Type: {name}")
        print(f"Count: {count}")
        print(f"Ratio: {ratio:.2f}%")


if __name__ == "__main__":
    main()
