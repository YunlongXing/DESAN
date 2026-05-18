#!/usr/bin/env bash

set -euo pipefail

DESAN_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DESAN_ROOT="$(cd "${DESAN_SCRIPT_DIR}/.." && pwd)"
DESAN_OUT_DIR="${DESAN_OUT_DIR:-${DESAN_ROOT}/out}"
PASS_NAME="${PASS_NAME:-desan-collect-checks}"
PLUGIN="${PLUGIN:-${DESAN_ROOT}/build/DESANPass.so}"

desan_die() {
  echo "error: $*" >&2
  exit 1
}

desan_note() {
  echo "[desan] $*" >&2
}

desan_find_tool() {
  local env_name="$1"
  shift

  local override="${!env_name:-}"
  if [[ -n "${override}" ]]; then
    echo "${override}"
    return 0
  fi

  local candidate
  for candidate in "$@"; do
    if command -v "${candidate}" >/dev/null 2>&1; then
      command -v "${candidate}"
      return 0
    fi
  done

  return 1
}

LLVM_CONFIG_BIN="${DESAN_LLVM_CONFIG:-${LLVM_CONFIG:-}}"
if [[ -z "${LLVM_CONFIG_BIN}" ]]; then
  LLVM_CONFIG_BIN="$(desan_find_tool LLVM_CONFIG llvm-config-18 llvm-config-17 llvm-config-16 llvm-config || true)"
fi

OPT_BIN="${DESAN_OPT:-${OPT:-}}"
if [[ -z "${OPT_BIN}" ]]; then
  OPT_BIN="$(desan_find_tool OPT opt-18 opt-17 opt-16 opt || true)"
fi

CLANG_BIN="${DESAN_CLANG:-${CLANG:-}}"
if [[ -z "${CLANG_BIN}" ]]; then
  CLANG_BIN="$(desan_find_tool CLANG clang-18 clang-17 clang-16 clang || true)"
fi

CLANGXX_BIN="${DESAN_CLANGXX:-${CLANGXX:-${CXX:-}}}"
if [[ -z "${CLANGXX_BIN}" ]]; then
  CLANGXX_BIN="$(desan_find_tool CLANGXX clang++-18 clang++-17 clang++-16 clang++ || true)"
fi

desan_require_tool() {
  local value="$1"
  local description="$2"
  [[ -n "${value}" ]] || desan_die "cannot find ${description}; set the matching environment variable"
}

desan_abs_path() {
  local path="$1"
  if [[ "${path}" = /* ]]; then
    echo "${path}"
  else
    echo "$(pwd)/${path}"
  fi
}

desan_is_cxx_source() {
  case "$1" in
    *.cc | *.cpp | *.cxx | *.c++ | *.C | *.CPP | *.CXX) return 0 ;;
    *) return 1 ;;
  esac
}

desan_compiler_for_source() {
  if desan_is_cxx_source "$1"; then
    desan_require_tool "${CLANGXX_BIN}" "clang++"
    echo "${CLANGXX_BIN}"
  else
    desan_require_tool "${CLANG_BIN}" "clang"
    echo "${CLANG_BIN}"
  fi
}

DESAN_CXX_STDLIB_CFLAGS=()
DESAN_CXX_STDLIB_LDFLAGS=()
DESAN_CXX_STDLIB_GXX="${DESAN_CXX_STDLIB_GXX:-g++}"
if command -v "${DESAN_CXX_STDLIB_GXX}" >/dev/null 2>&1; then
  gcc_version="$("${DESAN_CXX_STDLIB_GXX}" -dumpversion)"
  gcc_triple="$("${DESAN_CXX_STDLIB_GXX}" -dumpmachine)"
  for dir in \
    "/usr/include/c++/${gcc_version}" \
    "/usr/include/${gcc_triple}/c++/${gcc_version}" \
    "/usr/include/c++/${gcc_version}/backward" \
    "/usr/lib/gcc/${gcc_triple}/${gcc_version}/include"; do
    if [[ -d "${dir}" ]]; then
      DESAN_CXX_STDLIB_CFLAGS+=("-isystem" "${dir}")
    fi
  done
  if [[ -d "/usr/lib/gcc/${gcc_triple}/${gcc_version}" ]]; then
    DESAN_CXX_STDLIB_LDFLAGS+=("-L/usr/lib/gcc/${gcc_triple}/${gcc_version}")
  fi
  unset gcc_version gcc_triple dir
fi

DESAN_ENV_CFLAGS=()
DESAN_ENV_LDFLAGS=()
if [[ -n "${CFLAGS:-}" ]]; then
  # shellcheck disable=SC2206
  DESAN_ENV_CFLAGS=(${CFLAGS})
fi
if [[ -n "${LDFLAGS:-}" ]]; then
  # shellcheck disable=SC2206
  DESAN_ENV_LDFLAGS=(${LDFLAGS})
fi

desan_configure_sanitizer() {
  local sanitizer="$1"

  SAN_SUFFIX=""
  SANITIZER_FLAG=""
  SAN_EXTRA_IR_FLAGS=()
  SAN_EXTRA_OBJECT_FLAGS=()
  SAN_EXTRA_LINK_FLAGS=()
  SAN_CHECK_REGEX=""

  case "${sanitizer}" in
    asan | address)
      SAN_SUFFIX="asan"
      SANITIZER_FLAG="address"
      if [[ "${DESAN_ASAN_RECOVER:-0}" == "1" ]]; then
        SAN_EXTRA_IR_FLAGS+=("-fsanitize-recover=address")
        SAN_EXTRA_OBJECT_FLAGS+=("-fsanitize-recover=address")
        SAN_EXTRA_LINK_FLAGS+=("-fsanitize-recover=address")
      fi
      SAN_CHECK_REGEX='__asan_(report_(load|store)|load|store|exp_load|exp_store|memcpy|memmove|memset)'
      ;;
    ubsan | undefined)
      SAN_SUFFIX="ubsan"
      SANITIZER_FLAG="undefined"
      SAN_CHECK_REGEX='(__ubsan_handle_|llvm\.ubsantrap)'
      ;;
    msan | memory)
      SAN_SUFFIX="msan"
      SANITIZER_FLAG="memory"
      SAN_EXTRA_IR_FLAGS=("-fPIE")
      SAN_EXTRA_OBJECT_FLAGS=("-fPIE")
      SAN_EXTRA_LINK_FLAGS=("-fPIE" "-pie")
      SAN_CHECK_REGEX='__msan_(warning|maybe_warning|param_|retval_|va_arg_|check_mem_is_initialized|test_shadow|print_shadow)'
      ;;
    none | native | unsanitized)
      SAN_SUFFIX="native"
      SANITIZER_FLAG=""
      SAN_CHECK_REGEX='a^'
      ;;
    *)
      desan_die "unknown sanitizer '${sanitizer}'"
      ;;
  esac
}

desan_ensure_plugin() {
  [[ -f "${PLUGIN}" ]] || desan_die "pass plugin not found: ${PLUGIN}; run scripts/build.sh first or set PLUGIN=/path/to/DESANPass.so"
}

desan_make_ir() {
  local sanitizer="$1"
  local source="$2"
  local output_ll="$3"
  shift 3

  desan_configure_sanitizer "${sanitizer}"
  local compiler
  compiler="$(desan_compiler_for_source "${source}")"

  local flags=(
    "-fsanitize=${SANITIZER_FLAG}"
    "-O0"
    "-g"
    "-fno-discard-value-names"
    "-S"
    "-emit-llvm"
    "${SAN_EXTRA_IR_FLAGS[@]}"
    "${DESAN_ENV_CFLAGS[@]}"
  )
  if desan_is_cxx_source "${source}"; then
    flags+=("${DESAN_CXX_STDLIB_CFLAGS[@]}")
  fi

  mkdir -p "$(dirname "${output_ll}")"
  desan_note "emitting sanitizer IR: ${output_ll}"
  "${compiler}" "${flags[@]}" "$@" "${source}" -o "${output_ll}"
}

desan_link_ir() {
  local sanitizer="$1"
  local source="$2"
  local input_ir="$3"
  local output_bin="$4"
  shift 4

  desan_configure_sanitizer "${sanitizer}"
  local compiler
  compiler="$(desan_compiler_for_source "${source}")"

  local flags=(
    "-fsanitize=${SANITIZER_FLAG}"
    "${SAN_EXTRA_LINK_FLAGS[@]}"
    "${DESAN_ENV_LDFLAGS[@]}"
  )
  if desan_is_cxx_source "${source}"; then
    flags+=("${DESAN_CXX_STDLIB_LDFLAGS[@]}")
  fi

  mkdir -p "$(dirname "${output_bin}")"
  local object_file="${OBJECT_FILE:-${output_bin}.o}"
  desan_note "lowering IR to object: ${object_file}"
  "${compiler}" -c "${input_ir}" "${SAN_EXTRA_OBJECT_FLAGS[@]}" -o "${object_file}"

  desan_note "linking sanitizer runtime binary: ${output_bin}"
  "${compiler}" "${object_file}" "${flags[@]}" "$@" -o "${output_bin}"
}

desan_run_pipeline() {
  local sanitizer="$1"
  local source="${2:-}"
  local output_bin="${3:-}"

  [[ -n "${source}" ]] || desan_die "missing source file"
  [[ -f "${source}" ]] || desan_die "source file does not exist: ${source}"

  desan_configure_sanitizer "${sanitizer}"
  local source_abs
  source_abs="$(desan_abs_path "${source}")"
  local stem
  stem="$(basename "${source_abs}")"
  stem="${stem%.*}"

  mkdir -p "${DESAN_OUT_DIR}"
  local raw_ll="${RAW_LL:-${DESAN_OUT_DIR}/${stem}_${SAN_SUFFIX}.ll}"
  local opt_ll="${OPT_LL:-${DESAN_OUT_DIR}/${stem}_${SAN_SUFFIX}_opt.ll}"
  local bin="${output_bin:-${DESAN_OUT_DIR}/${stem}_${SAN_SUFFIX}_opt}"

  desan_make_ir "${sanitizer}" "${source_abs}" "${raw_ll}"
  "${DESAN_SCRIPT_DIR}/run_pass.sh" "${raw_ll}" "${opt_ll}"
  desan_link_ir "${sanitizer}" "${source_abs}" "${opt_ll}" "${bin}"

  echo "raw_ir=${raw_ll}"
  echo "optimized_ir=${opt_ll}"
  echo "binary=${bin}"
}

desan_count_checks() {
  local sanitizer="$1"
  local ir_file="$2"

  desan_configure_sanitizer "${sanitizer}"
  local count
  set +e
  count="$(grep -E "^[[:space:]]*([^=]+=[[:space:]]*)?((tail|musttail|notail)[[:space:]]+)?(call|invoke)[[:space:]].*@(${SAN_CHECK_REGEX})" "${ir_file}" 2>/dev/null | wc -l | tr -d ' ')"
  set -e
  echo "${count:-0}"
}
