#!/usr/bin/env bash

set -euo pipefail

cd /home/dragon/DESAN

cp spec_configs/cpu2006-desan.cfg spec/speccpu2006-v1.0.1/config/desan.cfg
sed -i 's/-std=gnu++03/-std=gnu++98/g' spec/speccpu2006-v1.0.1/config/desan.cfg
grep -q '^env_vars' spec/speccpu2006-v1.0.1/config/desan.cfg ||
  printf '\nenv_vars      = 1\n' >> spec/speccpu2006-v1.0.1/config/desan.cfg
set +u
pushd spec/speccpu2006-v1.0.1 >/dev/null
source ./shrc
popd >/dev/null
set -u

export ASAN_OPTIONS="${ASAN_OPTIONS:-detect_leaks=0:strict_string_checks=0:strict_memcmp=0:halt_on_error=0:abort_on_error=0:exitcode=0}"
export LSAN_OPTIONS="${LSAN_OPTIONS:-detect_leaks=0}"
export DESAN_SPEC_FALLBACK="${DESAN_SPEC_FALLBACK:-1}"
export DESAN_SPEC_QUIET="${DESAN_SPEC_QUIET:-1}"
export DESAN_SPEC_RECORD_IR_ON_DISABLE="${DESAN_SPEC_RECORD_IR_ON_DISABLE:-1}"
export DESAN_SPEC_DISABLE_PASS=1
export DESAN_SPEC_KEEP_VALUE_NAMES="${DESAN_SPEC_KEEP_VALUE_NAMES:-0}"
export DESAN_ASAN_RECOVER="${DESAN_ASAN_RECOVER:-1}"
export DESAN_SPEC_LINK_CC="${DESAN_SPEC_LINK_CC:-clang-18}"
export DESAN_SPEC_LINK_CXX="${DESAN_SPEC_LINK_CXX:-clang++-18}"
export DESAN_CXX_STDLIB_GXX="${DESAN_CXX_STDLIB_GXX:-g++-12}"
export LDFLAGS="${LDFLAGS:-} -no-pie"

ASANMM_ROOT="${ASANMM_ROOT:-/home/dragon/ASAN--}"
ASANMM_CLANG="${ASANMM_CLANG:-${ASANMM_ROOT}/llvm-4.0.0-project/ASan--Build/bin/clang}"
ASANMM_CLANGXX="${ASANMM_CLANGXX:-${ASANMM_ROOT}/llvm-4.0.0-project/ASan--Build/bin/clang++}"
VANILLA_CLANG="${VANILLA_CLANG:-${ASANMM_ROOT}/vanilla_llvm/ASan_Build/bin/clang}"
VANILLA_CLANGXX="${VANILLA_CLANGXX:-${ASANMM_ROOT}/vanilla_llvm/ASan_Build/bin/clang++}"

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
  find spec/speccpu2006-v1.0.1/benchspec/CPU2006 -path '*/run/run_base_test_desan.*' -type d -prune -exec rm -rf {} +
  set +e
  if [[ "${RUNSPEC_ACTION:-run}" == "build" ]]; then
    runspec --action=build --config=desan --size=test --tune=base --iterations=1 --rebuild all
  else
    runspec --config=desan --size=test --tune=base --iterations=1 --rebuild all
  fi
  local status=$?
  set -e
  echo "=== CPU2006 ${label} status=${status} ==="
  return 0
}

NATIVE_OUT=/home/dragon/DESAN/out/spec-cpu2006-asanmm-native
BASE_OUT=/home/dragon/DESAN/out/spec-cpu2006-asanmm-asan-base
ASANMM_OUT=/home/dragon/DESAN/out/spec-cpu2006-asanmm-after-check-elimination
SUMMARY_MD=/home/dragon/DESAN/out/spec-cpu2006-asanmm-after-check-elimination-summary.md
SUMMARY_CSV=/home/dragon/DESAN/out/spec-cpu2006-asanmm-after-check-elimination-summary.csv

RUN_NATIVE="${RUN_NATIVE:-1}"
RUN_BASE="${RUN_BASE:-1}"
RUN_ASANMM="${RUN_ASANMM:-1}"

if [[ "${RUN_NATIVE}" == "1" ]]; then
  rm -rf "${NATIVE_OUT}"
  mkdir -p "${NATIVE_OUT}"
  export DESAN_OUT_DIR="${NATIVE_OUT}"
  export DESAN_SPEC_SANITIZER=none
  export CLANG="${VANILLA_CLANG}"
  export CLANGXX="${VANILLA_CLANGXX}"
  run_one native
  if [[ "${RUNSPEC_ACTION:-run}" != "build" ]]; then
    copy_latest_results "${NATIVE_OUT}"
  fi
fi

if [[ "${RUN_BASE}" == "1" ]]; then
  rm -rf "${BASE_OUT}"
  mkdir -p "${BASE_OUT}"
  export DESAN_OUT_DIR="${BASE_OUT}"
  export DESAN_SPEC_SANITIZER=asan
  export CLANG="${VANILLA_CLANG}"
  export CLANGXX="${VANILLA_CLANGXX}"
  run_one asan-base
  if [[ "${RUNSPEC_ACTION:-run}" != "build" ]]; then
    copy_latest_results "${BASE_OUT}"
  fi
fi

if [[ "${RUN_ASANMM}" == "1" ]]; then
  rm -rf "${ASANMM_OUT}"
  mkdir -p "${ASANMM_OUT}"
  export DESAN_OUT_DIR="${ASANMM_OUT}"
  export DESAN_SPEC_SANITIZER=asan
  export CLANG="${ASANMM_CLANG}"
  export CLANGXX="${ASANMM_CLANGXX}"
  run_one asanmm
  if [[ "${RUNSPEC_ACTION:-run}" != "build" ]]; then
    copy_latest_results "${ASANMM_OUT}"
  fi
fi

python3 scripts/spec_asanmm_summary.py \
  --suite CPU2006 \
  --base-records "${BASE_OUT}/spec-logs/compile_records.tsv" \
  --asanmm-records "${ASANMM_OUT}/spec-logs/compile_records.tsv" \
  --native-csv "${NATIVE_OUT}/spec-results/CINT2006.*.test.csv" \
  --native-csv "${NATIVE_OUT}/spec-results/CFP2006.*.test.csv" \
  --base-csv "${BASE_OUT}/spec-results/CINT2006.*.test.csv" \
  --base-csv "${BASE_OUT}/spec-results/CFP2006.*.test.csv" \
  --asanmm-csv "${ASANMM_OUT}/spec-results/CINT2006.*.test.csv" \
  --asanmm-csv "${ASANMM_OUT}/spec-results/CFP2006.*.test.csv" \
  --csv-out "${SUMMARY_CSV}" \
  > "${SUMMARY_MD}"

cat "${SUMMARY_MD}"
