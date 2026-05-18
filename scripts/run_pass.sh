#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

usage() {
  cat >&2 <<'USAGE'
Usage: scripts/run_pass.sh INPUT.ll OUTPUT.{ll|bc} [extra opt/pass flags...]

Runs the DESAN sanitizer-check optimizer pass.

Environment:
  OPT              opt executable, e.g. opt-18
  PLUGIN           pass plugin path, default build/DESANPass.so
  PASS_NAME        pass pipeline name, default desan-collect-checks
  DESAN_PASS_ARGS  additional opt flags, e.g. "-desan-dump-removals=false"
  DESAN_POST_OPT_PASSES
                   optional post-DESAN opt pipeline, e.g.
                   "sroa,early-cse,instcombine,simplifycfg,gvn,adce,dce,bdce,loop-simplify,loop-mssa(licm)"
USAGE
}

if (($# < 2)); then
  usage
  exit 2
fi

input_ir="$1"
output_ir="$2"
shift 2

[[ -f "${input_ir}" ]] || desan_die "input IR does not exist: ${input_ir}"
desan_require_tool "${OPT_BIN}" "opt"
desan_ensure_plugin

DESAN_POST_OPT_PASSES="${DESAN_POST_OPT_PASSES:-sroa,early-cse,instcombine,simplifycfg,gvn,adce,dce,bdce,loop-simplify,loop-mssa(licm)}"

env_pass_args=()
if [[ -n "${DESAN_PASS_ARGS:-}" ]]; then
  # shellcheck disable=SC2206
  env_pass_args=(${DESAN_PASS_ARGS})
fi

format_args=()
case "${output_ir}" in
  *.ll) format_args=("-S") ;;
esac

mkdir -p "$(dirname "${output_ir}")"
desan_note "running pass: ${input_ir} -> ${output_ir}"

pass_output="${output_ir}"
tmp_output=""
if [[ -n "${DESAN_POST_OPT_PASSES:-}" ]]; then
  tmp_output="$(mktemp "${output_ir}.desan.XXXXXX")"
  pass_output="${tmp_output}"
fi

"${OPT_BIN}" \
  -load-pass-plugin="${PLUGIN}" \
  "-passes=${PASS_NAME}" \
  "${env_pass_args[@]}" \
  "$@" \
  "${format_args[@]}" \
  "${input_ir}" \
  -o "${pass_output}"

if [[ -n "${DESAN_POST_OPT_PASSES:-}" ]]; then
  desan_note "running post opt pipeline: ${DESAN_POST_OPT_PASSES}"
  "${OPT_BIN}" \
    "-passes=${DESAN_POST_OPT_PASSES}" \
    "${format_args[@]}" \
    "${pass_output}" \
    -o "${output_ir}"
  rm -f "${pass_output}"
fi
