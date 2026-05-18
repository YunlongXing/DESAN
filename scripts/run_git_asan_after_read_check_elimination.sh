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

GIT_SANITIZER="${GIT_SANITIZER:-asan}"
GIT_REPO="${GIT_REPO:-https://github.com/git/git.git}"
GIT_REF="${GIT_REF:-v2.45.2}"
GIT_SRC="${GIT_SRC:-/home/dragon/DESAN/benchmarks/git-src}"
OUT_ROOT="${OUT_ROOT:-/home/dragon/DESAN/out/git-${GIT_SANITIZER}-after-read-check-elimination}"
RUNS="${RUNS:-5}"
GIT_BENCH_FILES="${GIT_BENCH_FILES:-1200}"
GIT_WORKLOAD_LOOPS="${GIT_WORKLOAD_LOOPS:-20}"
JOBS="${JOBS:-2}"
SUMMARY_MD="${SUMMARY_MD:-/home/dragon/DESAN/out/git-${GIT_SANITIZER}-after-read-check-elimination-summary.md}"
SUMMARY_CSV="${SUMMARY_CSV:-/home/dragon/DESAN/out/git-${GIT_SANITIZER}-after-read-check-elimination-summary.csv}"
RUNTIME_CSV="${OUT_ROOT}/runtime.csv"

case "${GIT_SANITIZER}" in
  asan | address)
    GIT_SANITIZER="asan"
    CORE_PREFIX_ARGS=(
      --core-prefix __asan_report_load
      --core-prefix __asan_report_store
      --core-prefix __asan_load
      --core-prefix __asan_store
    )
    ;;
  ubsan | undefined)
    GIT_SANITIZER="ubsan"
    CORE_PREFIX_ARGS=(
      --core-prefix __ubsan_handle_type_mismatch
      --core-prefix __ubsan_handle_pointer_overflow
      --core-prefix __ubsan_handle_out_of_bounds
      --core-prefix __ubsan_handle_shift_out_of_bounds
    )
    ;;
  msan | memory | memsan)
    GIT_SANITIZER="msan"
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
    echo "unknown GIT_SANITIZER=${GIT_SANITIZER}" >&2
    exit 2
    ;;
esac

GIT_MAKE_FLAGS=(
  NO_OPENSSL=YesPlease
  NO_CURL=YesPlease
  NO_EXPAT=YesPlease
  NO_GETTEXT=YesPlease
  NO_TCLTK=YesPlease
  NO_PERL=YesPlease
  NO_PYTHON=YesPlease
  NO_INSTALL_HARDLINKS=YesPlease
)

prepare_source() {
  mkdir -p "$(dirname "${GIT_SRC}")"
  if [[ ! -d "${GIT_SRC}/.git" ]]; then
    rm -rf "${GIT_SRC}"
    git clone --depth 1 --branch "${GIT_REF}" "${GIT_REPO}" "${GIT_SRC}"
  else
    git -C "${GIT_SRC}" fetch --depth 1 origin "${GIT_REF}"
    git -C "${GIT_SRC}" checkout -f FETCH_HEAD
    git -C "${GIT_SRC}" clean -fdx
  fi
}

copy_source_tree() {
  local build_dir="$1"
  rm -rf "${build_dir}"
  mkdir -p "${build_dir}"
  tar -C "${GIT_SRC}" --exclude .git -cf - . | tar -C "${build_dir}" -xf -
}

configure_and_build() {
  local label="$1"
  local sanitizer="$2"
  local disable_pass="$3"
  local build_dir="${OUT_ROOT}/build-${label}"

  echo "=== Git ${label} build ==="
  copy_source_tree "${build_dir}"

  export DESAN_OUT_DIR="${OUT_ROOT}/${label}"
  export DESAN_SPEC_BENCHMARK=git
  export DESAN_SPEC_SANITIZER="${sanitizer}"
  export DESAN_SPEC_DISABLE_PASS="${disable_pass}"
  mkdir -p "${DESAN_OUT_DIR}"

  (
    cd "${build_dir}"
    make -j"${JOBS}" git \
      CC=/home/dragon/DESAN/scripts/spec_desan_cc.sh \
      CFLAGS="-O0 -g -fno-omit-frame-pointer" \
      "${GIT_MAKE_FLAGS[@]}"
  )
  echo "=== Git ${label} build done ==="
}

prepare_workload_repo() {
  local repo="${OUT_ROOT}/bench/repo"
  local i dir
  rm -rf "${repo}" "${OUT_ROOT}/bench/home"
  mkdir -p "${repo}" "${OUT_ROOT}/bench/home"

  (
    cd "${repo}"
    /usr/bin/git init -q
    /usr/bin/git config user.email desan@example.com
    /usr/bin/git config user.name DESAN
    for i in $(seq 1 "${GIT_BENCH_FILES}"); do
      dir="dir$((i % 32))"
      mkdir -p "${dir}"
      printf 'file=%04d needle=%04d\nline two %04d\n' "${i}" "$((i % 97))" "${i}" >"${dir}/file_${i}.txt"
    done
    /usr/bin/git add .
    /usr/bin/git commit -q -m "seed benchmark repository"
    local modify_count=50
    if [[ "${GIT_BENCH_FILES}" -lt "${modify_count}" ]]; then
      modify_count="${GIT_BENCH_FILES}"
    fi
    for i in $(seq 1 "${modify_count}"); do
      printf 'modified=%04d\n' "${i}" >>"dir$((i % 32))/file_${i}.txt"
    done
  )
}

time_workload_once() {
  local app="$1"
  local build_dir="$2"
  local repo="${OUT_ROOT}/bench/repo"
  GIT_CONFIG_NOSYSTEM=1 \
    GIT_TEMPLATE_DIR=/usr/share/git-core/templates \
    GIT_EXEC_PATH="${build_dir}" \
    HOME="${OUT_ROOT}/bench/home" \
    /usr/bin/time -f "%e" sh -c '
      set -e
      app="$1"
      repo="$2"
      loops="$3"
      i=1
      while [ "${i}" -le "${loops}" ]; do
        "${app}" -C "${repo}" status --porcelain >/dev/null
        "${app}" -C "${repo}" diff --stat >/dev/null
        "${app}" -C "${repo}" ls-files >/dev/null
        "${app}" -C "${repo}" grep -n "needle" -- "*.txt" >/dev/null
        "${app}" -C "${repo}" rev-list --all --objects >/dev/null
        i=$((i + 1))
      done
    ' sh "${app}" "${repo}" "${GIT_WORKLOAD_LOOPS}"
}

run_runtime() {
  local label="$1"
  local build_dir="${OUT_ROOT}/build-${label}"
  local app="${build_dir}/git"
  local run

  [[ -x "${app}" ]] || {
    echo "missing Git app for ${label}: ${app}" >&2
    return 1
  }

  for run in $(seq 1 "${RUNS}"); do
    local time_log="${OUT_ROOT}/bench/${label}-${run}.time"
    local status="S"
    local seconds=""
    if ! time_workload_once "${app}" "${build_dir}" 2>"${time_log}"; then
      status="RE"
    fi
    seconds="$(tail -n 1 "${time_log}" | tr -d '[:space:]' || true)"
    printf '%s,%s,%s,%s\n' "${label}" "${run}" "${status}" "${seconds}" >>"${RUNTIME_CSV}"
  done
}

rm -rf "${OUT_ROOT}" "${SUMMARY_MD}" "${SUMMARY_CSV}"
mkdir -p "${OUT_ROOT}"

prepare_source
prepare_workload_repo

run_native="${RUN_NATIVE:-1}"
run_base="${RUN_BASE:-1}"
run_desan="${RUN_DESAN:-1}"

if [[ "${run_native}" == "1" ]]; then
  configure_and_build native none 1
fi
if [[ "${run_base}" == "1" ]]; then
  configure_and_build "${GIT_SANITIZER}-base" "${GIT_SANITIZER}" 1
fi
if [[ "${run_desan}" == "1" ]]; then
  configure_and_build desan "${GIT_SANITIZER}" 0
fi

printf 'Variant,Run,Status,Seconds\n' >"${RUNTIME_CSV}"
run_runtime native
run_runtime "${GIT_SANITIZER}-base"
run_runtime desan

python3 scripts/opensource_summary.py \
  --suite OpenSource \
  --benchmark git \
  --records "${OUT_ROOT}/desan/spec-logs/compile_records.tsv" \
  --runtime-csv "${RUNTIME_CSV}" \
  --before-variant "${GIT_SANITIZER}-base" \
  --after-variant desan \
  "${CORE_PREFIX_ARGS[@]}" \
  --csv-out "${SUMMARY_CSV}" \
  >"${SUMMARY_MD}"

cat "${SUMMARY_MD}"
