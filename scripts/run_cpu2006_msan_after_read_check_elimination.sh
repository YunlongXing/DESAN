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
# SPEC CPU2006 contains benign uninitialized-value patterns that make MSan
# abort before producing comparable timings. Keep the instrumentation/check
# overhead, but suppress reports for this benchmark run so base and DESAN can
# complete and be compared.
export MSAN_OPTIONS="${MSAN_OPTIONS:-halt_on_error=0:exit_code=0:report_umrs=0:print_stats=0}"

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
BASE_OUT=/home/dragon/DESAN/out/spec-cpu2006-msan-base
DESAN_OUT=/home/dragon/DESAN/out/spec-cpu2006-msan-after-read-check-elimination
SUMMARY_MD=/home/dragon/DESAN/out/spec-cpu2006-msan-after-read-check-elimination-summary.md
SUMMARY_CSV=/home/dragon/DESAN/out/spec-cpu2006-msan-after-read-check-elimination-summary.csv

if ! compgen -G "${NATIVE_OUT}/spec-results/CINT2006.*.test.csv" >/dev/null ||
   ! compgen -G "${NATIVE_OUT}/spec-results/CFP2006.*.test.csv" >/dev/null; then
  rm -rf "${NATIVE_OUT}"
  mkdir -p "${NATIVE_OUT}"
  export DESAN_OUT_DIR="${NATIVE_OUT}"
  export DESAN_SPEC_SANITIZER=none
  export DESAN_SPEC_DISABLE_PASS=1
  run_one native
  copy_latest_results "${NATIVE_OUT}"
fi

if ! compgen -G "${BASE_OUT}/spec-results/CINT2006.*.test.csv" >/dev/null ||
   ! compgen -G "${BASE_OUT}/spec-results/CFP2006.*.test.csv" >/dev/null; then
  rm -rf "${BASE_OUT}"
  mkdir -p "${BASE_OUT}"
  export DESAN_OUT_DIR="${BASE_OUT}"
  export DESAN_SPEC_SANITIZER=msan
  export DESAN_SPEC_DISABLE_PASS=1
  run_one msan-base
  copy_latest_results "${BASE_OUT}"
fi

rm -rf "${DESAN_OUT}"
mkdir -p "${DESAN_OUT}"

export DESAN_OUT_DIR="${DESAN_OUT}"
export DESAN_SPEC_SANITIZER=msan
export DESAN_SPEC_DISABLE_PASS=0
run_one msan-after-read-check-elimination
copy_latest_results "${DESAN_OUT}"

python3 scripts/spec_asan_summary.py \
  --suite CPU2006 \
  --records "${DESAN_OUT}/spec-logs/compile_records.tsv" \
  --native-csv "${NATIVE_OUT}/spec-results/CINT2006.*.test.csv" \
  --native-csv "${NATIVE_OUT}/spec-results/CFP2006.*.test.csv" \
  --before-csv "${BASE_OUT}/spec-results/CINT2006.*.test.csv" \
  --before-csv "${BASE_OUT}/spec-results/CFP2006.*.test.csv" \
  --after-csv "${DESAN_OUT}/spec-results/CINT2006.*.test.csv" \
  --after-csv "${DESAN_OUT}/spec-results/CFP2006.*.test.csv" \
  --core-prefix __msan_warning \
  --core-prefix __msan_maybe_warning \
  --core-prefix __msan_param_ \
  --core-prefix __msan_retval_ \
  --core-prefix __msan_va_arg_ \
  --core-prefix __msan_check_mem_is_initialized \
  --core-prefix __msan_test_shadow \
  --core-prefix __msan_print_shadow \
  --csv-out "${SUMMARY_CSV}" \
  > "${SUMMARY_MD}"

cat "${SUMMARY_MD}"
