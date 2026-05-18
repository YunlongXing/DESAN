#!/usr/bin/env bash

set -euo pipefail

ROOT="${ROOT:-/home/dragon/DESAN}"
SANRAZOR_HOME="${SANRAZOR_HOME:-/home/dragon/SanRazor}"
SANRAZOR_LEVEL="${SANRAZOR_LEVEL:-L2}"
SPEC_SIZE="${SPEC_SIZE:-test}"
SANRAZOR_REUSE_BASE="${SANRAZOR_REUSE_BASE:-0}"

SANRAZOR_LLVM="${SANRAZOR_LLVM:-${SANRAZOR_HOME}/toolchain/clang+llvm-9.0.1-x86_64-linux-gnu-ubuntu-16.04}"
SANRAZOR_BIN="${SANRAZOR_BIN:-${SANRAZOR_HOME}/sr-bin}"
SANRAZOR_PLUGIN_DIR="${SANRAZOR_PLUGIN_DIR:-${SANRAZOR_HOME}/build-srpass}"
SANRAZOR_SPEC_DIR="${SANRAZOR_SPEC_DIR:-${SANRAZOR_HOME}/data/spec}"
SPEC_DIR="${SPEC_DIR:-${ROOT}/spec/speccpu2006-v1.0.1}"

OUT_ROOT="${OUT_ROOT:-${ROOT}/out}"
NATIVE_OUT="${NATIVE_OUT:-${OUT_ROOT}/spec-cpu2006-sanrazor-ubsan-native}"
BASE_OUT="${BASE_OUT:-${OUT_ROOT}/spec-cpu2006-sanrazor-ubsan-base}"
SANRAZOR_OUT="${SANRAZOR_OUT:-${OUT_ROOT}/spec-cpu2006-sanrazor-ubsan-${SANRAZOR_LEVEL}}"
SUMMARY_MD="${SUMMARY_MD:-${OUT_ROOT}/spec-cpu2006-sanrazor-ubsan-${SANRAZOR_LEVEL}-summary.md}"
SUMMARY_CSV="${SUMMARY_CSV:-${OUT_ROOT}/spec-cpu2006-sanrazor-ubsan-${SANRAZOR_LEVEL}-summary.csv}"

BENCHMARKS=(
  401.bzip2
  429.mcf
  445.gobmk
  456.hmmer
  458.sjeng
  462.libquantum
  433.milc
  470.lbm
  482.sphinx3
  444.namd
  453.povray
)

require_file() {
  local path="$1"
  local label="$2"
  [[ -e "${path}" ]] || {
    echo "missing ${label}: ${path}" >&2
    exit 1
  }
}

prepare_env() {
  require_file "${SANRAZOR_BIN}/SanRazor-clang" "SanRazor-clang"
  require_file "${SANRAZOR_BIN}/SanRazor-clang++" "SanRazor-clang++"
  require_file "${SANRAZOR_PLUGIN_DIR}/SRPass.so" "SRPass.so"
  require_file "${SANRAZOR_SPEC_DIR}/SR_on.cfg" "SanRazor SR_on.cfg"
  require_file "${SANRAZOR_SPEC_DIR}/SR_off.cfg" "SanRazor SR_off.cfg"
  require_file "${SPEC_DIR}/shrc" "SPEC CPU2006 shrc"

  export PATH="${SANRAZOR_BIN}:${SANRAZOR_LLVM}/bin:${PATH}"
  export LD_LIBRARY_PATH="${SANRAZOR_PLUGIN_DIR}:${SANRAZOR_LLVM}/lib:${LD_LIBRARY_PATH:-}"
  export ASAN_OPTIONS="${ASAN_OPTIONS:-alloc_dealloc_mismatch=0:detect_leaks=0:halt_on_error=0}"
  export UBSAN_OPTIONS="${UBSAN_OPTIONS:-halt_on_error=0:print_stacktrace=0}"
}

source_spec() {
  set +u
  pushd "${SPEC_DIR}" >/dev/null
  # shellcheck disable=SC1091
  source ./shrc
  popd >/dev/null
  set -u
}

copy_latest_results() {
  local out_dir="$1"
  mkdir -p "${out_dir}/spec-results"
  local latest_int latest_fp prefix path
  latest_int="$(ls -t "${SPEC_DIR}"/result/CINT2006.*."${SPEC_SIZE}".rsf 2>/dev/null | head -n 1 || true)"
  latest_fp="$(ls -t "${SPEC_DIR}"/result/CFP2006.*."${SPEC_SIZE}".rsf 2>/dev/null | head -n 1 || true)"
  for path in "${latest_int}" "${latest_fp}"; do
    [[ -n "${path}" ]] || continue
    prefix="${path%.rsf}"
    cp "${prefix}.rsf" "${out_dir}/spec-results/"
    [[ -f "${prefix}.txt" ]] && cp "${prefix}.txt" "${out_dir}/spec-results/"
    [[ -f "${prefix}.csv" ]] && cp "${prefix}.csv" "${out_dir}/spec-results/"
  done
  return 0
}

copy_check_logs() {
  local out_dir="$1"
  mkdir -p "${out_dir}/sanrazor-checks"
  local bench copied
  copied=0
  for bench in "${BENCHMARKS[@]}"; do
    local latest
    latest="$(find "${SPEC_DIR}/benchspec/CPU2006/${bench}/run" \
      -path "*/build_peak_SR_ubsan_${SANRAZOR_LEVEL}.*" \
      -type f -name check.txt -print 2>/dev/null | sort | tail -n 1 || true)"
    if [[ -n "${latest}" ]]; then
      mkdir -p "${out_dir}/sanrazor-checks/${bench}"
      cp "${latest}" "${out_dir}/sanrazor-checks/${bench}/check.txt"
      copied=$((copied + 1))
    else
      echo "warning: no check.txt found for ${bench} ${SANRAZOR_LEVEL}" >&2
    fi
  done
  echo "=== copied ${copied} SanRazor check logs for ${SANRAZOR_LEVEL} ==="
  return 0
}

has_result_rsfs() {
  local out_dir="$1"
  compgen -G "${out_dir}/spec-results/CINT2006.*.${SPEC_SIZE}.rsf" >/dev/null &&
    compgen -G "${out_dir}/spec-results/CFP2006.*.${SPEC_SIZE}.rsf" >/dev/null
}

run_off() {
  local sanitizer="$1"
  local out_dir="$2"
  if [[ "${SANRAZOR_REUSE_BASE}" == "1" ]] && has_result_rsfs "${out_dir}"; then
    echo "=== CPU2006 SanRazor comparison: ${sanitizer} reuse existing results ==="
    return 0
  fi
  echo "=== CPU2006 SanRazor comparison: ${sanitizer} ==="
  rm -rf "${out_dir}"
  mkdir -p "${out_dir}"
  pushd "${SANRAZOR_SPEC_DIR}" >/dev/null
  set +e
  ./run_spec.sh "${sanitizer}" "${SPEC_SIZE}" >"${out_dir}/${sanitizer}.log" 2>&1
  local status=$?
  set -e
  popd >/dev/null
  echo "=== ${sanitizer} status=${status} ==="
  copy_latest_results "${out_dir}"
}

run_sanrazor() {
  local out_dir="$1"
  echo "=== CPU2006 SanRazor comparison: ubsan ${SANRAZOR_LEVEL} ==="
  rm -rf "${out_dir}"
  mkdir -p "${out_dir}"
  pushd "${SANRAZOR_SPEC_DIR}" >/dev/null
  set +e
  ./run_spec_SR.sh ubsan "${SANRAZOR_LEVEL}" "${SPEC_SIZE}" >"${out_dir}/sanrazor-ubsan-${SANRAZOR_LEVEL}.log" 2>&1
  local status=$?
  set -e
  popd >/dev/null
  echo "=== SanRazor ubsan ${SANRAZOR_LEVEL} status=${status} ==="
  copy_latest_results "${out_dir}"
  copy_check_logs "${out_dir}"
}

prepare_env
source_spec

run_off default "${NATIVE_OUT}"
run_off ubsan "${BASE_OUT}"
run_sanrazor "${SANRAZOR_OUT}"

python3 "${ROOT}/scripts/spec_sanrazor_summary.py" \
  --suite CPU2006 \
  --level "${SANRAZOR_LEVEL}" \
  --check-glob "${SANRAZOR_OUT}/sanrazor-checks/*/check.txt" \
  --native-csv "${NATIVE_OUT}/spec-results/CINT2006.*.${SPEC_SIZE}.rsf" \
  --native-csv "${NATIVE_OUT}/spec-results/CFP2006.*.${SPEC_SIZE}.rsf" \
  --base-csv "${BASE_OUT}/spec-results/CINT2006.*.${SPEC_SIZE}.rsf" \
  --base-csv "${BASE_OUT}/spec-results/CFP2006.*.${SPEC_SIZE}.rsf" \
  --sanrazor-csv "${SANRAZOR_OUT}/spec-results/CINT2006.*.${SPEC_SIZE}.rsf" \
  --sanrazor-csv "${SANRAZOR_OUT}/spec-results/CFP2006.*.${SPEC_SIZE}.rsf" \
  --csv-out "${SUMMARY_CSV}" \
  >"${SUMMARY_MD}"

cat "${SUMMARY_MD}"
