#!/usr/bin/env bash

set -euo pipefail

cd /home/dragon/DESAN

export LLVM_CONFIG="${LLVM_CONFIG:-llvm-config-18}"
export OPT="${OPT:-opt-18}"
export CLANG="${CLANG:-clang-18}"
export CLANGXX="${CLANGXX:-clang++-18}"
export PLUGIN="${PLUGIN:-/home/dragon/DESAN/build/DESANPass.so}"
export DESAN_SPEC_FALLBACK="${DESAN_SPEC_FALLBACK:-1}"
export DESAN_SPEC_PASS_TIMEOUT="${DESAN_SPEC_PASS_TIMEOUT:-900}"
export DESAN_SPEC_QUIET="${DESAN_SPEC_QUIET:-1}"
export DESAN_PASS_ARGS="${DESAN_PASS_ARGS:--desan-core-top-n=0 -desan-core-min-ratio=0}"
export ASAN_OPTIONS="${ASAN_OPTIONS:-detect_leaks=0:alloc_dealloc_mismatch=0}"
export LSAN_OPTIONS="${LSAN_OPTIONS:-detect_leaks=0}"
export UBSAN_OPTIONS="${UBSAN_OPTIONS:-halt_on_error=0:print_stacktrace=0}"
export MSAN_OPTIONS="${MSAN_OPTIONS:-halt_on_error=0:exit_code=0:report_umrs=0:print_stats=0}"

OPENSSL_SANITIZER="${OPENSSL_SANITIZER:-asan}"
OPENSSL_REPO="${OPENSSL_REPO:-https://github.com/openssl/openssl.git}"
OPENSSL_REF="${OPENSSL_REF:-openssl-3.3.2}"
OPENSSL_SRC="${OPENSSL_SRC:-/home/dragon/DESAN/benchmarks/openssl-src}"
OUT_ROOT="${OUT_ROOT:-/home/dragon/DESAN/out/openssl-${OPENSSL_SANITIZER}-after-read-check-elimination}"
RUNS="${RUNS:-5}"
INPUT_MB="${INPUT_MB:-64}"
JOBS="${JOBS:-2}"
SUMMARY_MD="${SUMMARY_MD:-/home/dragon/DESAN/out/openssl-${OPENSSL_SANITIZER}-after-read-check-elimination-summary.md}"
SUMMARY_CSV="${SUMMARY_CSV:-/home/dragon/DESAN/out/openssl-${OPENSSL_SANITIZER}-after-read-check-elimination-summary.csv}"
RUNTIME_CSV="${OUT_ROOT}/runtime.csv"

case "${OPENSSL_SANITIZER}" in
  asan | address)
    OPENSSL_SANITIZER="asan"
    CORE_PREFIX_ARGS=(
      --core-prefix __asan_report_load
      --core-prefix __asan_report_store
      --core-prefix __asan_load
      --core-prefix __asan_store
    )
    ;;
  ubsan | undefined)
    OPENSSL_SANITIZER="ubsan"
    CORE_PREFIX_ARGS=(
      --core-prefix __ubsan_handle_type_mismatch
      --core-prefix __ubsan_handle_pointer_overflow
      --core-prefix __ubsan_handle_out_of_bounds
      --core-prefix __ubsan_handle_shift_out_of_bounds
    )
    ;;
  msan | memory | memsan)
    OPENSSL_SANITIZER="msan"
    CORE_PREFIX_ARGS=(
      --core-prefix __msan_warning
      --core-prefix __msan_maybe_warning
      --core-prefix __msan_param_
      --core-prefix __msan_retval_
      --core-prefix __msan_va_arg_
      --core-prefix __msan_check_mem_is_initialized
      --core-prefix __msan_test_shadow
      --core-prefix __msan_print_shadow
    )
    ;;
  *)
    echo "unknown OPENSSL_SANITIZER=${OPENSSL_SANITIZER}" >&2
    exit 2
    ;;
esac

prepare_source() {
  mkdir -p "$(dirname "${OPENSSL_SRC}")"
  if [[ ! -d "${OPENSSL_SRC}/.git" ]]; then
    rm -rf "${OPENSSL_SRC}"
    git clone --depth 1 --branch "${OPENSSL_REF}" "${OPENSSL_REPO}" "${OPENSSL_SRC}"
  else
    git -C "${OPENSSL_SRC}" fetch --depth 1 origin "${OPENSSL_REF}"
    git -C "${OPENSSL_SRC}" checkout -f FETCH_HEAD
    git -C "${OPENSSL_SRC}" clean -fdx
  fi
}

copy_source_tree() {
  local build_dir="$1"
  rm -rf "${build_dir}"
  mkdir -p "${build_dir}"
  tar -C "${OPENSSL_SRC}" --exclude .git -cf - . | tar -C "${build_dir}" -xf -
}

configure_and_build() {
  local label="$1"
  local sanitizer="$2"
  local disable_pass="$3"
  local build_dir="${OUT_ROOT}/build-${label}"

  echo "=== OpenSSL ${label} build ==="
  copy_source_tree "${build_dir}"

  export DESAN_OUT_DIR="${OUT_ROOT}/${label}"
  export DESAN_SPEC_BENCHMARK=openssl
  export DESAN_SPEC_SANITIZER="${sanitizer}"
  export DESAN_SPEC_DISABLE_PASS="${disable_pass}"
  mkdir -p "${DESAN_OUT_DIR}"

  (
    cd "${build_dir}"
    CC=/home/dragon/DESAN/scripts/spec_desan_cc.sh \
      ./Configure linux-x86_64 no-shared no-module no-tests no-asm -O0 -g -fno-omit-frame-pointer
    make -j"${JOBS}" build_sw
  )
  echo "=== OpenSSL ${label} build done ==="
}

prepare_input() {
  mkdir -p "${OUT_ROOT}/bench"
  local input="${OUT_ROOT}/bench/input-${INPUT_MB}m.bin"
  if [[ ! -f "${input}" ]]; then
    dd if=/dev/zero of="${input}" bs=1M count="${INPUT_MB}" status=none
  fi
}

time_workload_once() {
  local app="$1"
  local input="$2"
  local tmp_out="$3"
  /usr/bin/time -f "%e" sh -c \
    "\"${app}\" dgst -sha256 \"${input}\" >/dev/null && \"${app}\" enc -aes-256-cbc -nosalt -K 000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f -iv 000102030405060708090a0b0c0d0e0f -in \"${input}\" -out \"${tmp_out}\" >/dev/null"
}

run_runtime() {
  local label="$1"
  local build_dir="${OUT_ROOT}/build-${label}"
  local app="${build_dir}/apps/openssl"
  local input="${OUT_ROOT}/bench/input-${INPUT_MB}m.bin"
  local run

  [[ -x "${app}" ]] || {
    echo "missing OpenSSL app for ${label}: ${app}" >&2
    return 1
  }

  for run in $(seq 1 "${RUNS}"); do
    local tmp_out="${OUT_ROOT}/bench/${label}-${run}.enc"
    local time_log="${OUT_ROOT}/bench/${label}-${run}.time"
    local status="S"
    local seconds=""
    if ! time_workload_once "${app}" "${input}" "${tmp_out}" 2>"${time_log}"; then
      status="RE"
    fi
    seconds="$(tail -n 1 "${time_log}" | tr -d '[:space:]' || true)"
    rm -f "${tmp_out}"
    printf '%s,%s,%s,%s\n' "${label}" "${run}" "${status}" "${seconds}" >>"${RUNTIME_CSV}"
  done
}

rm -rf "${OUT_ROOT}" "${SUMMARY_MD}" "${SUMMARY_CSV}"
mkdir -p "${OUT_ROOT}"

prepare_source
prepare_input

run_native="${RUN_NATIVE:-1}"
run_base="${RUN_BASE:-1}"
run_desan="${RUN_DESAN:-1}"

if [[ "${run_native}" == "1" ]]; then
  configure_and_build native none 1
fi
if [[ "${run_base}" == "1" ]]; then
  configure_and_build "${OPENSSL_SANITIZER}-base" "${OPENSSL_SANITIZER}" 1
fi
if [[ "${run_desan}" == "1" ]]; then
  configure_and_build desan "${OPENSSL_SANITIZER}" 0
fi

printf 'Variant,Run,Status,Seconds\n' >"${RUNTIME_CSV}"
run_runtime native
run_runtime "${OPENSSL_SANITIZER}-base"
run_runtime desan

python3 scripts/opensource_summary.py \
  --suite OpenSource \
  --benchmark openssl \
  --records "${OUT_ROOT}/desan/spec-logs/compile_records.tsv" \
  --runtime-csv "${RUNTIME_CSV}" \
  --before-variant "${OPENSSL_SANITIZER}-base" \
  --after-variant desan \
  "${CORE_PREFIX_ARGS[@]}" \
  --csv-out "${SUMMARY_CSV}" \
  >"${SUMMARY_MD}"

cat "${SUMMARY_MD}"
