#!/usr/bin/env bash

set -euo pipefail

cd /home/dragon/DESAN

cp spec_configs/cpu2006-desan.cfg spec/speccpu2006-v1.0.1/config/desan.cfg
set +u
pushd spec/speccpu2006-v1.0.1 >/dev/null
source ./shrc
popd >/dev/null
set -u

export LLVM_CONFIG="${LLVM_CONFIG:-llvm-config-18}"
export OPT="${OPT:-opt-18}"
export CLANG="${CLANG:-clang-18}"
export CLANGXX="${CLANGXX:-clang++-18}"
export PLUGIN="${PLUGIN:-/home/dragon/DESAN/build/DESANPass.so}"
export DESAN_SPEC_FALLBACK="${DESAN_SPEC_FALLBACK:-1}"
export DESAN_SPEC_PASS_TIMEOUT="${DESAN_SPEC_PASS_TIMEOUT:-900}"
export DESAN_SPEC_QUIET="${DESAN_SPEC_QUIET:-1}"
export DESAN_PASS_ARGS="${DESAN_PASS_ARGS:--desan-core-top-n=0 -desan-core-min-ratio=0}"
export ASAN_OPTIONS="${ASAN_OPTIONS:-detect_leaks=0}"
export LSAN_OPTIONS="${LSAN_OPTIONS:-detect_leaks=0}"

copy_latest_results() {
  local out_dir="$1"
  mkdir -p "${out_dir}/spec-results"

  local latest
  if latest="$(ls -t spec/speccpu2006-v1.0.1/result/CINT2006.*.test.csv 2>/dev/null | head -n 1)" &&
     [[ -n "${latest}" ]]; then
    cp "${latest}" "${out_dir}/spec-results/"
  fi
  if latest="$(ls -t spec/speccpu2006-v1.0.1/result/CFP2006.*.test.csv 2>/dev/null | head -n 1)" &&
     [[ -n "${latest}" ]]; then
    cp "${latest}" "${out_dir}/spec-results/"
  fi
}

has_cpu2006_results() {
  local out_dir="$1"
  compgen -G "${out_dir}/spec-results/CINT2006.*.test.csv" >/dev/null &&
    compgen -G "${out_dir}/spec-results/CFP2006.*.test.csv" >/dev/null
}

run_one() {
  local label="$1"
  echo "=== CPU2006 ${label} ==="
  set +e
  runspec --config=desan --size=test --tune=base --iterations=1 --rebuild all
  local status=$?
  set -e
  echo "=== CPU2006 ${label} status=${status} ==="
  return 0
}

NATIVE_OUT=/home/dragon/DESAN/out/spec-cpu2006-native
BASE_OUT=/home/dragon/DESAN/out/spec-cpu2006-asan-base
DESAN_OUT=/home/dragon/DESAN/out/spec-cpu2006-asan-after-read-check-elimination
SUMMARY_MD=/home/dragon/DESAN/out/spec-cpu2006-asan-after-read-check-elimination-summary.md
SUMMARY_CSV=/home/dragon/DESAN/out/spec-cpu2006-asan-after-read-check-elimination-summary.csv

run_native="${RUN_NATIVE:-auto}"
run_base="${RUN_BASE:-auto}"
run_desan="${RUN_DESAN:-1}"

if [[ "${run_native}" == "1" ]] ||
   { [[ "${run_native}" == "auto" ]] && ! has_cpu2006_results "${NATIVE_OUT}"; }; then
  rm -rf "${NATIVE_OUT}"
  mkdir -p "${NATIVE_OUT}"
  export DESAN_OUT_DIR="${NATIVE_OUT}"
  export DESAN_SPEC_SANITIZER=none
  export DESAN_SPEC_DISABLE_PASS=1
  run_one native
  copy_latest_results "${NATIVE_OUT}"
fi

if [[ "${run_base}" == "1" ]] ||
   { [[ "${run_base}" == "auto" ]] && ! has_cpu2006_results "${BASE_OUT}"; }; then
  rm -rf "${BASE_OUT}"
  mkdir -p "${BASE_OUT}"
  export DESAN_OUT_DIR="${BASE_OUT}"
  export DESAN_SPEC_SANITIZER=asan
  export DESAN_SPEC_DISABLE_PASS=1
  run_one asan-base
  copy_latest_results "${BASE_OUT}"
fi

if [[ "${run_desan}" == "1" ]]; then
  rm -rf "${DESAN_OUT}"
  mkdir -p "${DESAN_OUT}"

  export DESAN_OUT_DIR="${DESAN_OUT}"
  export DESAN_SPEC_SANITIZER=asan
  export DESAN_SPEC_DISABLE_PASS=0
  run_one after-read-check-elimination
  copy_latest_results "${DESAN_OUT}"
fi

python3 scripts/spec_asan_summary.py \
  --suite CPU2006 \
  --records "${DESAN_OUT}/spec-logs/compile_records.tsv" \
  --native-csv "${NATIVE_OUT}/spec-results/CINT2006.*.test.csv" \
  --native-csv "${NATIVE_OUT}/spec-results/CFP2006.*.test.csv" \
  --before-csv "${BASE_OUT}/spec-results/CINT2006.*.test.csv" \
  --before-csv "${BASE_OUT}/spec-results/CFP2006.*.test.csv" \
  --after-csv "${DESAN_OUT}/spec-results/CINT2006.*.test.csv" \
  --after-csv "${DESAN_OUT}/spec-results/CFP2006.*.test.csv" \
  --csv-out "${SUMMARY_CSV}" \
  > "${SUMMARY_MD}"

cat "${SUMMARY_MD}"
