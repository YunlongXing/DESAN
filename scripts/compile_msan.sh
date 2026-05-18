#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

usage() {
  cat >&2 <<'USAGE'
Usage: scripts/compile_msan.sh SOURCE.[c|cc|cpp] [OUTPUT_BINARY]

Pipeline:
  clang -fsanitize=memory -fPIE -O0 -S -emit-llvm SOURCE -o out/*_msan.ll
  scripts/run_pass.sh out/*_msan.ll out/*_msan_opt.ll
  clang -c -fPIE out/*_msan_opt.ll -o out/*_msan_opt.o
  clang -fsanitize=memory -fPIE -pie out/*_msan_opt.o -o OUTPUT_BINARY

MSan requires a compiler/runtime build that supports MemorySanitizer.
USAGE
}

if (($# < 1 || $# > 2)); then
  usage
  exit 2
fi

desan_run_pipeline msan "$@"
