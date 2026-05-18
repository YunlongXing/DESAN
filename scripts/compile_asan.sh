#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

usage() {
  cat >&2 <<'USAGE'
Usage: scripts/compile_asan.sh SOURCE.[c|cc|cpp] [OUTPUT_BINARY]

Pipeline:
  clang -fsanitize=address -O0 -S -emit-llvm SOURCE -o out/*_asan.ll
  scripts/run_pass.sh out/*_asan.ll out/*_asan_opt.ll
  clang -c out/*_asan_opt.ll -o out/*_asan_opt.o
  clang -fsanitize=address out/*_asan_opt.o -o OUTPUT_BINARY
USAGE
}

if (($# < 1 || $# > 2)); then
  usage
  exit 2
fi

desan_run_pipeline asan "$@"
