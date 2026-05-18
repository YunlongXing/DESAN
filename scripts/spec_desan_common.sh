#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

DESAN_SPEC_SANITIZER="${DESAN_SPEC_SANITIZER:-asan}"
DESAN_SPEC_IR_DIR="${DESAN_SPEC_IR_DIR:-${DESAN_OUT_DIR}/spec-ir}"
DESAN_SPEC_LOG_DIR="${DESAN_SPEC_LOG_DIR:-${DESAN_OUT_DIR}/spec-logs}"
DESAN_SPEC_FALLBACK="${DESAN_SPEC_FALLBACK:-1}"
DESAN_SPEC_QUIET="${DESAN_SPEC_QUIET:-1}"
DESAN_SPEC_PASS_TIMEOUT="${DESAN_SPEC_PASS_TIMEOUT:-900}"
DESAN_SPEC_DISABLE_PASS="${DESAN_SPEC_DISABLE_PASS:-0}"
DESAN_SPEC_RECORD_IR_ON_DISABLE="${DESAN_SPEC_RECORD_IR_ON_DISABLE:-0}"
DESAN_SPEC_COMPILE_RECORDS="${DESAN_SPEC_COMPILE_RECORDS:-${DESAN_SPEC_LOG_DIR}/compile_records.tsv}"
DESAN_POST_OPT_PASSES="${DESAN_POST_OPT_PASSES:-sroa,early-cse,instcombine,simplifycfg,gvn,adce,dce,bdce,loop-simplify,loop-mssa(licm)}"
export DESAN_POST_OPT_PASSES

desan_spec_log() {
  if [[ "${DESAN_SPEC_QUIET}" != "1" ]]; then
    echo "[desan-spec] $*" >&2
  fi
}

desan_hash_text() {
  if command -v sha1sum >/dev/null 2>&1; then
    printf '%s' "$1" | sha1sum | awk '{print $1}'
  else
    printf '%s' "$1" | shasum -a 1 | awk '{print $1}'
  fi
}

desan_is_source_file() {
  case "$1" in
    *.c | *.C | *.cc | *.cpp | *.cxx | *.c++ | *.CPP | *.CXX) return 0 ;;
    *) return 1 ;;
  esac
}

desan_strip_unsupported_compile_arg() {
  case "$1" in
    -M | -MM | -E | -S) return 0 ;;
    *) return 1 ;;
  esac
}

desan_is_cxx_compiler() {
  local compiler_name
  compiler_name="$(basename "$1")"
  case "${compiler_name}" in
    *++* | *cxx* | *cpp*) return 0 ;;
    *) return 1 ;;
  esac
}

desan_spec_benchmark_name() {
  local cwd="$1"
  if [[ -n "${DESAN_SPEC_BENCHMARK:-}" ]]; then
    echo "${DESAN_SPEC_BENCHMARK}"
    return 0
  fi
  if [[ "${cwd}" =~ /benchspec/CPU2006/([^/]+)/ ]]; then
    echo "${BASH_REMATCH[1]}"
    return 0
  fi
  if [[ "${cwd}" =~ /benchspec/CPU/([^/]+)/ ]]; then
    echo "${BASH_REMATCH[1]}"
    return 0
  fi
  echo "<unknown>"
}

desan_spec_record_compile() {
  local status="$1"
  local compiler="$2"
  local source="$3"
  local output="$4"
  local raw_ll="$5"
  local opt_ll="$6"
  local pass_log="$7"

  mkdir -p "${DESAN_SPEC_LOG_DIR}"
  if [[ ! -f "${DESAN_SPEC_COMPILE_RECORDS}" ]]; then
    printf 'status\tsanitizer\tbenchmark\tcompiler\tcwd\tsource\toutput\traw_ll\topt_ll\tpass_log\n' >>"${DESAN_SPEC_COMPILE_RECORDS}"
  fi

  local cwd benchmark
  cwd="$(pwd)"
  benchmark="$(desan_spec_benchmark_name "${cwd}")"
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "${status}" "${DESAN_SPEC_SANITIZER}" "${benchmark}" "${compiler}" \
    "${cwd}" "${source}" "${output}" "${raw_ll}" "${opt_ll}" "${pass_log}" \
    >>"${DESAN_SPEC_COMPILE_RECORDS}"
}

desan_spec_c_or_cxx() {
  local compiler="$1"
  shift

  desan_configure_sanitizer "${DESAN_SPEC_SANITIZER}"

  local args=("$@")
  local filtered=()
  local compile_mode=0
  local output=""
  local source=""
  local passthrough=0
  local relocatable_link=0

  local i=0
  while [[ "${i}" -lt "${#args[@]}" ]]; do
    local arg="${args[$i]}"
    case "${arg}" in
      -c)
        compile_mode=1
        ;;
      -r)
        relocatable_link=1
        filtered+=("${arg}")
        ;;
      -o)
        i=$((i + 1))
        output="${args[$i]:-}"
        ;;
      -o*)
        output="${arg#-o}"
        ;;
      -*)
        if desan_strip_unsupported_compile_arg "${arg}"; then
          passthrough=1
        fi
        filtered+=("${arg}")
        ;;
      *)
        if desan_is_source_file "${arg}"; then
          source="${arg}"
        else
          filtered+=("${arg}")
        fi
        ;;
    esac
    i=$((i + 1))
  done

  local cxx_mode=0
  if desan_is_cxx_compiler "${compiler}" || { [[ -n "${source}" ]] && desan_is_cxx_source "${source}"; }; then
    cxx_mode=1
  fi

  local cxx_compile_flags=()
  local cxx_link_flags=()
  if [[ "${cxx_mode}" == "1" ]]; then
    cxx_compile_flags=("${DESAN_CXX_STDLIB_CFLAGS[@]}")
    cxx_link_flags=("${DESAN_CXX_STDLIB_LDFLAGS[@]}")
  fi

  if [[ "${compile_mode}" != "1" || -z "${source}" || "${passthrough}" == "1" ]]; then
    desan_spec_log "link/pass-through: ${compiler} ${args[*]}"
    local link_san_flags=()
    if [[ -n "${SANITIZER_FLAG}" && "${relocatable_link}" != "1" ]]; then
      link_san_flags=("-fsanitize=${SANITIZER_FLAG}" "${SAN_EXTRA_LINK_FLAGS[@]}")
    fi
    local link_compiler="${compiler}"
    if [[ "${compile_mode}" != "1" && "${passthrough}" != "1" ]]; then
      if [[ "${cxx_mode}" == "1" && -n "${DESAN_SPEC_LINK_CXX:-}" ]]; then
        link_compiler="${DESAN_SPEC_LINK_CXX}"
      elif [[ "${cxx_mode}" != "1" && -n "${DESAN_SPEC_LINK_CC:-}" ]]; then
        link_compiler="${DESAN_SPEC_LINK_CC}"
      fi
    fi
    "${link_compiler}" "${args[@]}" "${cxx_compile_flags[@]}" "${link_san_flags[@]}" "${DESAN_ENV_LDFLAGS[@]}" "${cxx_link_flags[@]}"
    return $?
  fi

  if [[ "${DESAN_SPEC_DISABLE_PASS}" == "1" ]]; then
    desan_spec_log "direct sanitizer compile: ${compiler} ${args[*]}"
    mkdir -p "${DESAN_SPEC_IR_DIR}" "${DESAN_SPEC_LOG_DIR}" "$(dirname "${output:-.}")"
    local raw_ll=""
    local pass_log=""
    local record_status="direct"
    if [[ "${DESAN_SPEC_RECORD_IR_ON_DISABLE}" == "1" && -n "${SANITIZER_FLAG}" ]]; then
      local key
      key="$(desan_hash_text "$(pwd)/${source}|${output}|${filtered[*]}|${DESAN_SPEC_SANITIZER}|direct")"
      local stem
      stem="$(basename "${source}")"
      stem="${stem%.*}.${key}"
      raw_ll="${DESAN_SPEC_IR_DIR}/${stem}.${SAN_SUFFIX}.ll"
      pass_log="${DESAN_SPEC_LOG_DIR}/${stem}.${SAN_SUFFIX}.checks.log"
      local ir_flags=(
        "-fsanitize=${SANITIZER_FLAG}"
        "-O0"
        "-g"
        "-S"
        "-emit-llvm"
        "${SAN_EXTRA_IR_FLAGS[@]}"
      )
      if [[ "${DESAN_SPEC_KEEP_VALUE_NAMES:-1}" != "0" ]]; then
        ir_flags+=("-fno-discard-value-names")
      fi
      if "${compiler}" "${filtered[@]}" "${cxx_compile_flags[@]}" "${ir_flags[@]}" "${source}" -o "${raw_ll}"; then
        "${SCRIPT_DIR}/count_sanitizer_checks.py" --sanitizer "${DESAN_SPEC_SANITIZER}" "${raw_ll}" >"${pass_log}" 2>&1 || true
        record_status="direct-ir"
      else
        echo "IR sidecar generation failed for ${source}" >"${pass_log}"
        record_status="direct-ir-fallback"
      fi
    fi
    desan_spec_record_compile "${record_status}" "${compiler}" "${source}" "${output}" "${raw_ll}" "" "${pass_log}"
    local compile_san_flags=()
    if [[ -n "${SANITIZER_FLAG}" ]]; then
      compile_san_flags=("-fsanitize=${SANITIZER_FLAG}" "${SAN_EXTRA_OBJECT_FLAGS[@]}")
    fi
    "${compiler}" "${args[@]}" "${cxx_compile_flags[@]}" "${compile_san_flags[@]}"
    return $?
  fi

  if [[ -z "${SANITIZER_FLAG}" ]]; then
    desan_spec_log "direct native compile: ${compiler} ${args[*]}"
    mkdir -p "${DESAN_SPEC_LOG_DIR}" "$(dirname "${output:-.}")"
    desan_spec_record_compile "direct-native" "${compiler}" "${source}" "${output}" "" "" ""
    "${compiler}" "${args[@]}" "${cxx_compile_flags[@]}"
    return $?
  fi

  desan_require_tool "${OPT_BIN}" "opt"
  desan_ensure_plugin

  if [[ -z "${output}" ]]; then
    output="$(basename "${source%.*}").o"
  fi

  mkdir -p "${DESAN_SPEC_IR_DIR}" "${DESAN_SPEC_LOG_DIR}" "$(dirname "${output}")"
  local key
  key="$(desan_hash_text "$(pwd)/${source}|${output}|${filtered[*]}|${DESAN_SPEC_SANITIZER}")"
  local stem
  stem="$(basename "${source}")"
  stem="${stem%.*}.${key}"
  local raw_ll="${DESAN_SPEC_IR_DIR}/${stem}.${SAN_SUFFIX}.ll"
  local opt_ll="${DESAN_SPEC_IR_DIR}/${stem}.${SAN_SUFFIX}.opt.ll"
  local pass_log="${DESAN_SPEC_LOG_DIR}/${stem}.${SAN_SUFFIX}.pass.log"

  local ir_flags=(
    "-fsanitize=${SANITIZER_FLAG}"
    "-O0"
    "-g"
    "-S"
    "-emit-llvm"
    "${SAN_EXTRA_IR_FLAGS[@]}"
  )
  if [[ "${DESAN_SPEC_KEEP_VALUE_NAMES:-1}" != "0" ]]; then
    ir_flags+=("-fno-discard-value-names")
  fi

  desan_spec_log "compile IR: ${source} -> ${raw_ll}"
  if ! "${compiler}" "${filtered[@]}" "${cxx_compile_flags[@]}" "${ir_flags[@]}" "${source}" -o "${raw_ll}"; then
    if [[ "${DESAN_SPEC_FALLBACK}" == "1" ]]; then
      echo "[desan-spec] IR compile failed; falling back to direct sanitizer compile for ${source}" >&2
      desan_spec_record_compile "ir-compile-fallback" "${compiler}" "${source}" "${output}" "${raw_ll}" "${opt_ll}" "${pass_log}"
      "${compiler}" "${args[@]}" "${cxx_compile_flags[@]}" "-fsanitize=${SANITIZER_FLAG}" "${SAN_EXTRA_OBJECT_FLAGS[@]}"
      return $?
    fi
    return 1
  fi

  desan_spec_log "run pass: ${raw_ll} -> ${opt_ll}"
  local pass_cmd=(
    "${SCRIPT_DIR}/run_pass.sh" "${raw_ll}" "${opt_ll}"
    -desan-dump-checked-vars=false
    -desan-dump-check-graphs=false
    -desan-dump-removals=false
  )
  local pass_status=0
  if command -v timeout >/dev/null 2>&1 && [[ "${DESAN_SPEC_PASS_TIMEOUT}" != "0" ]]; then
    timeout "${DESAN_SPEC_PASS_TIMEOUT}" "${pass_cmd[@]}" >"${pass_log}" 2>&1 || pass_status=$?
  else
    "${pass_cmd[@]}" >"${pass_log}" 2>&1 || pass_status=$?
  fi

  if [[ "${pass_status}" != "0" ]]; then
    if [[ "${DESAN_SPEC_FALLBACK}" == "1" ]]; then
      echo "[desan-spec] DESAN pass failed or timed out with status ${pass_status}; falling back to direct sanitizer compile for ${source}" >&2
      echo "DESAN_SPEC_FALLBACK status=${pass_status} source=${source}" >>"${DESAN_SPEC_LOG_DIR}/fallbacks.log"
      desan_spec_record_compile "pass-fallback" "${compiler}" "${source}" "${output}" "${raw_ll}" "${opt_ll}" "${pass_log}"
      "${compiler}" "${args[@]}" "${cxx_compile_flags[@]}" "-fsanitize=${SANITIZER_FLAG}" "${SAN_EXTRA_OBJECT_FLAGS[@]}"
      return $?
    fi
    return 1
  fi

  desan_spec_log "lower object: ${opt_ll} -> ${output}"
  if ! "${compiler}" -c "${opt_ll}" "${SAN_EXTRA_OBJECT_FLAGS[@]}" -o "${output}"; then
    if [[ "${DESAN_SPEC_FALLBACK}" == "1" ]]; then
      echo "[desan-spec] optimized IR lowering failed; falling back to direct sanitizer compile for ${source}" >&2
      desan_spec_record_compile "lower-fallback" "${compiler}" "${source}" "${output}" "${raw_ll}" "${opt_ll}" "${pass_log}"
      "${compiler}" "${args[@]}" "${cxx_compile_flags[@]}" "-fsanitize=${SANITIZER_FLAG}" "${SAN_EXTRA_OBJECT_FLAGS[@]}"
      return $?
    fi
    return 1
  fi

  desan_spec_record_compile "pass" "${compiler}" "${source}" "${output}" "${raw_ll}" "${opt_ll}" "${pass_log}"
}

desan_spec_fortran() {
  local compiler="${FC:-gfortran}"
  desan_configure_sanitizer "${DESAN_SPEC_SANITIZER}"
  local compile_mode=0
  local arg
  for arg in "$@"; do
    if [[ "${arg}" == "-c" ]]; then
      compile_mode=1
      break
    fi
  done
  local link_flags=()
  if [[ "${compile_mode}" != "1" ]]; then
    link_flags=("${DESAN_ENV_LDFLAGS[@]}")
  fi
  case "${DESAN_SPEC_SANITIZER}" in
    none | native | unsanitized)
      "${compiler}" "$@" "${link_flags[@]}"
      ;;
    asan | address | ubsan | undefined)
      "${compiler}" "$@" "-fsanitize=${SANITIZER_FLAG}" "${SAN_EXTRA_OBJECT_FLAGS[@]}" "${link_flags[@]}"
      ;;
    *)
      "${compiler}" "$@" "${link_flags[@]}"
      ;;
  esac
}
