#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

usage() {
  cat >&2 <<'USAGE'
Usage: scripts/compile_ubsan.sh SOURCE.[c|cc|cpp] [OUTPUT_BINARY]

Pipeline:
  clang -fsanitize=undefined -O0 -S -emit-llvm SOURCE -o out/*_ubsan.ll
  scripts/run_pass.sh out/*_ubsan.ll out/*_ubsan_opt.ll
  clang -c out/*_ubsan_opt.ll -o out/*_ubsan_opt.o
  clang -fsanitize=undefined out/*_ubsan_opt.o -o OUTPUT_BINARY
USAGE
}

if (($# < 1 || $# > 2)); then
  usage
  exit 2
fi

desan_run_pipeline ubsan "$@"
