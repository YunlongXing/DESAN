#!/usr/bin/env python3
import argparse
import csv
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from run_oss_batch_after_read_check_elimination import (
    OUT_BASE,
    PROJECTS as DESAN_PROJECTS,
    ROOT,
    copy_source,
    prepare_source,
    sh,
    write_bench_inputs,
)


CC_WRAPPER = ROOT / "scripts" / "spec_desan_cc.sh"
CXX_WRAPPER = ROOT / "scripts" / "spec_desan_cxx.sh"
ASANMM_ROOT = Path(os.environ.get("ASANMM_ROOT", "/home/dragon/ASAN--"))
ASANMM_CLANG = Path(os.environ.get("ASANMM_CLANG", str(ASANMM_ROOT / "llvm-4.0.0-project/ASan--Build/bin/clang")))
ASANMM_CLANGXX = Path(os.environ.get("ASANMM_CLANGXX", str(ASANMM_ROOT / "llvm-4.0.0-project/ASan--Build/bin/clang++")))
VANILLA_CLANG = Path(os.environ.get("VANILLA_CLANG", str(ASANMM_ROOT / "vanilla_llvm/ASan_Build/bin/clang")))
VANILLA_CLANGXX = Path(os.environ.get("VANILLA_CLANGXX", str(ASANMM_ROOT / "vanilla_llvm/ASan_Build/bin/clang++")))

DEFAULT_PROJECTS = [
    "bzip2",
    "capstone",
    "coreutils",
    "curl",
    "duktape",
    "flac",
    "grep",
    "gzip",
    "imagemagick",
    "libpng",
    "libvpx",
    "lz4",
    "make",
    "openssl",
    "redis",
    "tar",
    "xz",
    "zlib",
    "zopfli",
    "zstd",
]

PROJECTS = dict(DESAN_PROJECTS)
PROJECTS["bzip2"] = {
    **PROJECTS["bzip2"],
    "build": 'make -j"$JOBS" CC="$CC" CFLAGS="$CFLAGS" LDFLAGS="-no-pie" bzip2',
}
PROJECTS["coreutils"] = {
    **PROJECTS["coreutils"],
    "build": './configure CC="$CC" CFLAGS="$CFLAGS" --disable-nls --enable-no-install-program=stdbuf && gen_headers="$(awk -F: \'/^lib\\/.*\\.h:/{print $1}\' Makefile | sort -u)" && make $gen_headers src/version.h && sed -i \'/#include <string.h>/a #include "setlocale_null.h"\' lib/hard-locale.c && make -j"$JOBS" src/wc src/sort',
}
PROJECTS["libvpx"] = {
    **PROJECTS["libvpx"],
    "build": 'LDFLAGS= CC="$CC" CXX="$CXX" ./configure --disable-examples --disable-unit-tests --disable-docs --disable-install-docs --disable-optimizations --disable-vp9-highbitdepth --target=generic-gnu && LDFLAGS= make -j"$JOBS" libvpx.a',
}
PROJECTS["zstd"] = {
    **PROJECTS["zstd"],
    "build": 'make -j"$JOBS" CC="$CC" CFLAGS="$CFLAGS" ZSTD_NO_ASM=1 zstd',
}
PROJECTS["openssl"] = {
    "repo": "https://github.com/openssl/openssl.git",
    "ref": "openssl-3.3.2",
    "build": 'CC="$CC" ./Configure linux-x86_64 no-shared no-module no-tests no-asm -O0 -g -fno-omit-frame-pointer && make -j"$JOBS" build_sw',
    "artifact": "apps/openssl",
    "run": 'for i in $(seq 1 "$LOOPS"); do "$APP" dgst -sha256 "$BENCH/input.txt" >/dev/null; "$APP" enc -aes-256-cbc -nosalt -K 000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f -iv 000102030405060708090a0b0c0d0e0f -in "$BENCH/input.txt" -out "$BENCH/out.enc" >/dev/null; rm -f "$BENCH/out.enc"; done',
}


def parse_args():
    parser = argparse.ArgumentParser(description="Run ASAN-- comparison on open-source projects.")
    parser.add_argument("--projects", default=",".join(DEFAULT_PROJECTS), help="comma-separated project names")
    parser.add_argument("--runs", type=int, default=int(os.environ.get("RUNS", "3")))
    parser.add_argument("--loops", type=int, default=int(os.environ.get("OSS_WORKLOAD_LOOPS", "3")))
    parser.add_argument("--jobs", type=int, default=int(os.environ.get("JOBS", "2")))
    parser.add_argument("--build-timeout", type=int, default=int(os.environ.get("OSS_BUILD_TIMEOUT", "7200")))
    parser.add_argument("--run-timeout", type=int, default=int(os.environ.get("OSS_RUN_TIMEOUT", "300")))
    return parser.parse_args()


def base_env(name, label, out_dir, jobs):
    if label == "asanmm":
        clang = str(ASANMM_CLANG)
        clangxx = str(ASANMM_CLANGXX)
        sanitizer = "asan"
    elif label == "asan-base":
        clang = str(VANILLA_CLANG)
        clangxx = str(VANILLA_CLANGXX)
        sanitizer = "asan"
    elif label == "native":
        clang = str(VANILLA_CLANG)
        clangxx = str(VANILLA_CLANGXX)
        sanitizer = "none"
    else:
        raise ValueError(f"unknown label: {label}")

    env = os.environ.copy()
    env.update(
        {
            "LLVM_CONFIG": env.get("LLVM_CONFIG", "llvm-config-18"),
            "OPT": env.get("OPT", "opt-18"),
            "CLANG": clang,
            "CLANGXX": clangxx,
            "DESAN_LLVM_CONFIG": env.get("DESAN_LLVM_CONFIG", env.get("LLVM_CONFIG", "llvm-config-18")),
            "DESAN_OPT": env.get("DESAN_OPT", env.get("OPT", "opt-18")),
            "DESAN_CLANG": clang,
            "DESAN_CLANGXX": clangxx,
            "DESAN_SPEC_LINK_CC": env.get("DESAN_SPEC_LINK_CC", "clang-18"),
            "DESAN_SPEC_LINK_CXX": env.get("DESAN_SPEC_LINK_CXX", "clang++-18"),
            "DESAN_CXX_STDLIB_GXX": env.get("DESAN_CXX_STDLIB_GXX", "g++-12"),
            "PLUGIN": env.get("PLUGIN", str(ROOT / "build" / "DESANPass.so")),
            "DESAN_SPEC_FALLBACK": env.get("DESAN_SPEC_FALLBACK", "1"),
            "DESAN_SPEC_QUIET": env.get("DESAN_SPEC_QUIET", "1"),
            "DESAN_SPEC_RECORD_IR_ON_DISABLE": env.get("DESAN_SPEC_RECORD_IR_ON_DISABLE", "1"),
            "DESAN_SPEC_KEEP_VALUE_NAMES": env.get("DESAN_SPEC_KEEP_VALUE_NAMES", "0"),
            "DESAN_ASAN_RECOVER": env.get("DESAN_ASAN_RECOVER", "1"),
            "ASAN_OPTIONS": env.get(
                "ASAN_OPTIONS",
                "detect_leaks=0:strict_string_checks=0:strict_memcmp=0:halt_on_error=0:abort_on_error=0:exitcode=0",
            ),
            "LSAN_OPTIONS": env.get("LSAN_OPTIONS", "detect_leaks=0"),
            "LDFLAGS": (env.get("LDFLAGS", "") + " -no-pie").strip(),
            "CC": str(CC_WRAPPER),
            "CXX": str(CXX_WRAPPER),
            "CFLAGS": "-O0 -g -fno-omit-frame-pointer",
            "CXXFLAGS": "-O0 -g -fno-omit-frame-pointer",
            "JOBS": str(jobs),
            "DESAN_OUT_DIR": str(out_dir),
            "DESAN_SPEC_BENCHMARK": name,
            "DESAN_SPEC_SANITIZER": sanitizer,
            "DESAN_SPEC_DISABLE_PASS": "1",
        }
    )
    return env


def build_variant(name, project, src_dir, out_root, label, jobs, log, timeout):
    build_dir = out_root / f"build-{label}"
    copy_source(src_dir, build_dir)
    variant_out = out_root / label
    variant_out.mkdir(parents=True, exist_ok=True)
    env = base_env(name, label, variant_out, jobs)
    log.write(f"=== {name} {label} build ===\n")
    rc = sh(project["build"], cwd=build_dir, env=env, log=log, timeout=timeout)
    if rc != 0:
        raise RuntimeError(f"{name} {label} build failed with {rc}")
    log.write(f"=== {name} {label} build done ===\n")
    return build_dir


def run_runtime(name, project, label, build_dir, bench, runs, loops, timeout, csv_writer, log):
    artifact = project.get("artifact", "")
    app = build_dir / artifact if artifact else build_dir
    command = project.get("run", "")
    if artifact and not app.exists():
        log.write(f"missing artifact for {name} {label}: {app}\n")
        for run in range(1, runs + 1):
            csv_writer.writerow([label, run, "NR", ""])
        return

    env = os.environ.copy()
    env.update(
        {
            "APP": str(app),
            "BUILD": str(build_dir),
            "BENCH": str(bench),
            "LOOPS": str(loops),
            "ASAN_OPTIONS": env.get(
                "ASAN_OPTIONS",
                "detect_leaks=0:strict_string_checks=0:strict_memcmp=0:halt_on_error=0:abort_on_error=0:exitcode=0",
            ),
            "LSAN_OPTIONS": env.get("LSAN_OPTIONS", "detect_leaks=0"),
        }
    )
    for run in range(1, runs + 1):
        start = time.perf_counter()
        try:
            rc = sh(f"set -e; {command}", cwd=build_dir, env=env, log=log, timeout=timeout)
        except subprocess.TimeoutExpired:
            rc = 124
        elapsed = time.perf_counter() - start
        csv_writer.writerow([label, run, "S" if rc == 0 else "RE", f"{elapsed:.6f}"])


def summarize_one(name, out_root):
    summary_md = OUT_BASE / f"{name}-asanmm-after-check-elimination-summary.md"
    summary_csv = OUT_BASE / f"{name}-asanmm-after-check-elimination-summary.csv"
    cmd = [
        "python3",
        str(ROOT / "scripts" / "opensource_asanmm_summary.py"),
        "--suite",
        "OpenSource",
        "--benchmark",
        name,
        "--base-records",
        str(out_root / "asan-base" / "spec-logs" / "compile_records.tsv"),
        "--asanmm-records",
        str(out_root / "asanmm" / "spec-logs" / "compile_records.tsv"),
        "--runtime-csv",
        str(out_root / "runtime.csv"),
        "--csv-out",
        str(summary_csv),
    ]
    with summary_md.open("w") as out:
        subprocess.run(cmd, cwd=str(ROOT), stdout=out, stderr=subprocess.STDOUT, check=False)


def run_one(name, args, status_writer):
    project = PROJECTS[name]
    out_root = OUT_BASE / f"{name}-asanmm-after-check-elimination"
    log_path = OUT_BASE / f"{name}_asanmm_after_check_elimination.nohup.log"
    summary_status = "S"
    message = ""

    if out_root.exists():
        shutil.rmtree(out_root)
    for suffix in ("summary.md", "summary.csv"):
        p = OUT_BASE / f"{name}-asanmm-after-check-elimination-{suffix}"
        if p.exists():
            p.unlink()
    out_root.mkdir(parents=True, exist_ok=True)

    with log_path.open("w", buffering=1) as log:
        try:
            src_dir = prepare_source(name, project, log)
            bench = out_root / "bench"
            write_bench_inputs(bench)
            native_dir = build_variant(name, project, src_dir, out_root, "native", args.jobs, log, args.build_timeout)
            base_dir = build_variant(name, project, src_dir, out_root, "asan-base", args.jobs, log, args.build_timeout)
            asanmm_dir = build_variant(name, project, src_dir, out_root, "asanmm", args.jobs, log, args.build_timeout)
            runtime_csv = out_root / "runtime.csv"
            with runtime_csv.open("w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["Variant", "Run", "Status", "Seconds"])
                run_runtime(name, project, "native", native_dir, bench, args.runs, args.loops, args.run_timeout, writer, log)
                run_runtime(name, project, "asan-base", base_dir, bench, args.runs, args.loops, args.run_timeout, writer, log)
                run_runtime(name, project, "asanmm", asanmm_dir, bench, args.runs, args.loops, args.run_timeout, writer, log)
            summarize_one(name, out_root)
        except Exception as exc:
            summary_status = "FAIL"
            message = str(exc)
            log.write(f"FAILED: {message}\n")
    status_writer.writerow([name, summary_status, message])


def collect_results(projects):
    rows = []
    for project in projects:
        summary = OUT_BASE / f"{project}-asanmm-after-check-elimination-summary.csv"
        if not summary.exists():
            continue
        with summary.open(newline="", errors="replace") as f:
            rows.extend(csv.DictReader(f))
    out_csv = OUT_BASE / "oss-asanmm-after-check-elimination-results.csv"
    if rows:
        with out_csv.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    out_md = OUT_BASE / "oss-asanmm-after-check-elimination-results.md"
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
        "Overhead Reduction",
        "Status",
    ]
    with out_md.open("w") as f:
        f.write("| " + " | ".join(headers) + " |\n")
        f.write("|" + "|".join(["---"] * len(headers)) + "|\n")
        for row in rows:
            f.write(
                "| "
                + " | ".join(
                    [
                        row["Benchmark"],
                        row["Original Checks"],
                        row["ASAN-- Checks"],
                        row["Removed Checks"],
                        row["Removed / Original"],
                        row["Core / All Original"],
                        row["Removed Read Checks"],
                        row["Removed Store Checks"],
                        row["Runtime Native"],
                        row["Runtime ASan"],
                        row["Runtime ASAN--"],
                        row["Overhead Reduction %"],
                        f'{row["Native Status"]}->{row["ASan Status"]}->{row["ASAN-- Status"]}',
                    ]
                )
                + " |\n"
            )


def main():
    args = parse_args()
    projects = [p.strip() for p in args.projects.split(",") if p.strip()]
    for project in projects:
        if project not in PROJECTS:
            raise SystemExit(f"unknown project: {project}")
    for path in (ASANMM_CLANG, ASANMM_CLANGXX, VANILLA_CLANG, VANILLA_CLANGXX):
        if not path.exists():
            raise SystemExit(f"missing ASAN-- toolchain binary: {path}")

    OUT_BASE.mkdir(parents=True, exist_ok=True)
    status_path = Path(os.environ.get("OSS_ASANMM_STATUS_FILE", str(OUT_BASE / "oss-asanmm-after-check-elimination-status.csv")))
    with status_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Project", "Status", "Message"])
        for project in projects:
            print(f"=== {project} asanmm ===", flush=True)
            run_one(project, args, writer)
            f.flush()
    collect_results(DEFAULT_PROJECTS)


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "scripts"))
    main()
