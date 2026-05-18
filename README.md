# DESAN

DESAN is an LLVM IR artifact for reducing redundant sanitizer checks after
sanitizer instrumentation. It currently supports AddressSanitizer (ASan),
UndefinedBehaviorSanitizer (UBSan), and MemorySanitizer (MSan/MemSan).

The pass works on sanitizer-instrumented LLVM IR. It identifies sanitizer check
calls, traces the checked variable, classifies checks as READ, WRITE, or
UNKNOWN when possible, builds per-variable check graphs, removes redundant READ
checks under a conservative retention policy, and then removes the associated
sanitizer-only IR slice when safe.

This repository is intended to be a paper artifact. It contains source code,
scripts, small public tests, and summarized evaluation outputs. It does not
contain SPEC CPU 2006 or SPEC CPU 2017 source code, inputs, binaries, ISOs, or
archives, because SPEC CPU is commercial software.

## Artifact Layout

```text
include/DESAN/        C++ headers for the LLVM pass
lib/                  LLVM pass implementation
scripts/              Build, run, benchmark, and result aggregation scripts
spec_configs/         SPEC config templates; requires a local licensed SPEC install
test/inputs/          Small public test inputs
results/desan/        DESAN result summaries
results/asanmm-comparison/
                      ASAN-- comparison summaries
results/sanrazor-comparison/
                      SanRazor comparison summaries
```

Important result files:

- `results/desan/all-after-read-check-elimination-results.csv`
- `results/desan/spec/spec-cpu2006-*-summary.csv`
- `results/desan/spec/spec-cpu2017-*-summary.csv`
- `results/asanmm-comparison/*summary.csv`
- `results/sanrazor-comparison/*summary.csv`

## Requirements

DESAN is a new-pass-manager LLVM plugin.

Required:

- Linux or macOS
- CMake 3.20 or newer
- C++17 compiler
- LLVM/Clang with development headers and `opt`
- Python 3.8 or newer for result aggregation scripts
- Standard Unix tools: `bash`, `make`, `awk`, `sed`, `time`

Recommended:

- LLVM 17 or LLVM 18 for DESAN experiments
- `clang`, `clang++`, `opt`, and `llvm-config` from the same LLVM build
- `g++` on Linux, so CMake/Make can discover libstdc++ include and library
  directories for Clang builds

Sanitizer notes:

- ASan and UBSan work with normal Clang sanitizer runtimes.
- MSan requires an MSan-capable toolchain/runtime and usually an instrumented
  libc/libc++ environment for full real-world coverage.
- SPEC scripts require a licensed local SPEC CPU 2006/2017 installation. The
  benchmark distributions are not included in this repository.

## Build

Using CMake:

```bash
cmake -S . -B build -DLLVM_DIR=/path/to/llvm/lib/cmake/llvm
cmake --build build -j
```

Using `llvm-config`:

```bash
make LLVM_CONFIG=/path/to/llvm-config
```

The build produces:

```text
build/DESANPass.so
```

On Linux, the build system tries to add versioned libstdc++ paths discovered
from `g++`, such as `/usr/include/c++/<version>` and
`/usr/lib/gcc/<triple>/<version>`.

## Quick Start

Compile a test program to sanitizer-instrumented IR:

```bash
clang -O0 -g -fsanitize=address -S -emit-llvm \
  test/inputs/pipeline_sample.c -o /tmp/pipeline_asan.ll
```

Run DESAN:

```bash
opt -load-pass-plugin=build/DESANPass.so \
  -passes=desan-collect-checks \
  /tmp/pipeline_asan.ll -S -o /tmp/pipeline_asan_desan.ll
```

Recompile the optimized IR:

```bash
clang -fsanitize=address /tmp/pipeline_asan_desan.ll -o /tmp/pipeline_asan_desan
```

The helper scripts wrap these steps:

```bash
scripts/build.sh
scripts/compile_asan.sh test/inputs/pipeline_sample.c
scripts/compile_ubsan.sh test/inputs/pipeline_sample.c
scripts/compile_msan.sh test/inputs/pipeline_sample.c
scripts/evaluate.sh --runs 3 test/inputs/pipeline_sample.c
```

Useful environment variables:

```bash
LLVM_CONFIG=llvm-config-18
CLANG=clang-18
CLANGXX=clang++-18
OPT=opt-18
PLUGIN=build/DESANPass.so
PASS_NAME=desan-collect-checks
DESAN_OUT_DIR=out
DESAN_PASS_ARGS="-desan-dump-removals=true"
```

`scripts/run_pass.sh` also runs a post-DESAN optimization pipeline by default:

```text
sroa,early-cse,instcombine,simplifycfg,gvn,adce,dce,bdce,loop-simplify,loop-mssa(licm)
```

Override it with:

```bash
DESAN_POST_OPT_PASSES="instcombine,simplifycfg,dce" scripts/run_pass.sh in.ll out.ll
```

## Core Checks

The collector recognizes sanitizer runtime calls including:

ASan:

- `__asan_report_load*`
- `__asan_report_store*`
- `__asan_load*`
- `__asan_store*`
- `__asan_exp_load*`
- `__asan_exp_store*`
- `__asan_memcpy`, `__asan_memmove`, `__asan_memset`

UBSan:

- `__ubsan_handle_*`
- `llvm.ubsantrap`

MSan/MemSan:

- `__msan_warning*`
- `__msan_maybe_warning*`
- `__msan_param_*`
- `__msan_retval_*`
- `__msan_va_arg_*`
- `__msan_check_mem_is_initialized*`
- `__msan_test_shadow*`

Runtime initialization hooks such as sanitizer module constructors are not
counted as checks.

## Redundancy Policy

DESAN's current deletion policy is intentionally conservative:

1. Group checks by normalized checked variable and sanitizer kind.
2. Always keep WRITE checks.
3. Always keep UNKNOWN checks.
4. Keep the first check for each checked variable.
5. After a WRITE or UNKNOWN barrier, keep the next READ check.
6. Remove other READ checks for the same checked variable.
7. Remove the associated sanitizer-only slice when all uses stay inside the
   slice; otherwise fall back conservatively.

For ASan, load/report-load checks are READ and store/report-store checks are
WRITE. For UBSan and MSan, DESAN infers READ/WRITE from checked operands and IR
uses when possible; ambiguous cases remain UNKNOWN and are kept.

## SPEC CPU

SPEC CPU 2006 and SPEC CPU 2017 are commercial benchmarks. This repository
contains only config templates, scripts, and summarized outputs. To reproduce
SPEC experiments, install SPEC locally and point the scripts at that
installation.

Example:

```bash
SPEC_DIR=/path/to/speccpu2006-v1.0.1 \
  scripts/run_cpu2006_asan_after_read_check_elimination.sh

SPEC_DIR=/path/to/cpu2017-1.0.5 \
  scripts/run_cpu2017_ubsan_after_read_check_elimination.sh
```

The SPEC scripts expect the benchmark environment to be initialized by SPEC's
`shrc` and use `spec_configs/*.cfg` as templates.

## Open-Source Project Evaluation

The open-source benchmark runner downloads and builds public projects, then
evaluates native, sanitizer baseline, and DESAN binaries:

```bash
python3 scripts/run_oss_batch_after_read_check_elimination.py \
  --projects openssl,git,ffmpeg,imagemagick \
  --sanitizers asan,ubsan,msan \
  --runs 3
```

Aggregate result tables can be regenerated with:

```bash
python3 scripts/collect_all_results.py \
  --out-dir out \
  --csv-out out/all-after-read-check-elimination-results.csv
```

## Comparison Tools

ASAN-- comparison scripts:

```bash
scripts/run_cpu2006_asanmm_comparison.sh
scripts/run_cpu2017_asanmm_comparison.sh
python3 scripts/run_oss_asanmm_comparison.py --projects openssl,zlib,zstd
```

SanRazor comparison scripts:

```bash
SANRAZOR_LEVEL=L0 scripts/run_cpu2006_sanrazor_ubsan_comparison.sh
SANRAZOR_LEVEL=L1 scripts/run_cpu2006_sanrazor_ubsan_comparison.sh
SANRAZOR_LEVEL=L2 scripts/run_cpu2006_sanrazor_ubsan_comparison.sh
```

SanRazor reported removed checks are internal SC-accounting values. For the
paper tables in this artifact, SanRazor removed checks are counted as the
number of UBSan handler paths that the transformed IR actually disables
(`Detected Disabled`). The helper below computes READ/WRITE/UNKNOWN breakdowns:

```bash
python3 scripts/sanrazor_removed_access_summary.py \
  --spec-root /path/to/speccpu2006-v1.0.1 \
  --llvm-dis /path/to/llvm-dis \
  --level L0 --level L1 --level L2 \
  --csv-out out/spec-cpu2006-sanrazor-ubsan-removed-access-summary.csv
```

## Representative Results

DESAN summarized SPEC results:

| Suite | Sanitizer | Benchmarks | Original Checks | Core/All | Removed/Core | Weighted Overhead Reduction |
|---|---:|---:|---:|---:|---:|---:|
| CPU2006 | ASan | 31 | 568,963 | 94.05% | 61.50% | 19.54% |
| CPU2006 | UBSan | 22 | 1,438,462 | 84.84% | 54.03% | 42.29% |
| CPU2006 | MSan | 31 | 783,832 | 100.00% | 71.21% | 50.38% |
| CPU2017 | ASan | 47 | 2,106,782 | 95.86% | 59.89% | 5.63% |
| CPU2017 | UBSan | 47 | 4,934,790 | 87.31% | 53.59% | 25.95% |
| CPU2017 | MSan | 47 | 3,787,777 | 100.00% | 73.77% | -574.26% |

The CPU2017 MSan result is included for completeness; MSan measurements can be
noisy and highly sensitive to runtime/library setup.

ASAN-- comparison summary:

| Suite | Removed Checks | Removed/Original | Removed READ | Removed WRITE |
|---|---:|---:|---:|---:|
| CPU2006 | 254,233 | 32.40% | 67.84% | 31.94% |
| CPU2017 | 864,222 | 29.57% | 68.62% | 31.22% |

SanRazor UBSan comparison on CPU2006, using Detected Disabled as removed:

| Level | Removed Checks | Removed/Original | Removed READ | Removed WRITE | Removed UNKNOWN |
|---|---:|---:|---:|---:|---:|
| L0 | 63,174 | 29.30% | 28.52% | 6.36% | 65.12% |
| L1 | 80,722 | 37.32% | 31.66% | 9.95% | 58.39% |
| L2 | 110,755 | 51.37% | 27.64% | 9.06% | 63.29% |

Full CSV/Markdown outputs are in `results/`.

## Notes on Reproducibility

- The repository does not vendor LLVM, ASAN--, SanRazor, SPEC CPU, or sanitizer
  runtimes.
- The scripts expose path variables such as `SPEC_DIR`, `ASANMM_ROOT`,
  `SANRAZOR_HOME`, `LLVM_CONFIG`, `CLANG`, and `OPT` for local installations.
- Result tables are produced from specific local toolchain and benchmark runs;
  exact runtimes may vary across machines.
- Sanitizer detection consistency is checked by comparing whether the original
  sanitizer binary and the DESAN binary both report sanitizer-detected bugs.
