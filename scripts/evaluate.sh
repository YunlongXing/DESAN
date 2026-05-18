#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

usage() {
  cat >&2 <<'USAGE'
Usage:
  scripts/evaluate.sh [options] SOURCE.[c|cc|cpp] [-- program args...]
  scripts/evaluate.sh [options] SOURCE_DIR
  scripts/evaluate.sh --manifest benchmarks.manifest [options]

Builds original sanitizer binaries and DESAN-optimized binaries, then reports:
  total sanitizer checks, core checks, removed checks, removal ratio,
  binary size, runtime before/after, runtime overhead, and sanitizer
  detection consistency.

Options:
  --sanitizers LIST   Comma-separated list: asan,ubsan,msan. Default: all.
  --suite NAME        Suite label for single-source or directory mode.
  --manifest FILE     Manifest rows:
                        Suite|Benchmark|Sanitizers|Source|Args|ExpectDetect
                      Sanitizers may be all, asan, ubsan, msan, or a comma list.
                      ExpectDetect may be auto, yes, or no.
  --runs N            Number of timing runs. Default: RUNS env or 3.
  --timeout SEC       Timeout per run when timeout(1) exists. Default: none.
  --no-run            Build/count only; runtime and detection are N/A.
  --output FILE       Also write the Markdown table to FILE.
  -h, --help          Show this help.

Examples:
  scripts/evaluate.sh test/inputs/pipeline_sample.c
  scripts/evaluate.sh --sanitizers asan,ubsan test/inputs
  scripts/evaluate.sh --manifest test/inputs/eval_manifest.txt --runs 5
USAGE
}

SANITIZER_LIST="${SANITIZERS:-asan,ubsan,msan}"
SUITE_NAME="${SUITE:-single}"
MANIFEST=""
RUN_EVAL="${RUN:-1}"
RUNS_VALUE="${RUNS:-3}"
TIMEOUT_VALUE="${TIMEOUT:-}"
OUTPUT_FILE=""

while (($#)); do
  case "$1" in
    --sanitizers)
      [[ $# -ge 2 ]] || desan_die "--sanitizers requires a value"
      SANITIZER_LIST="$2"
      shift 2
      ;;
    --suite)
      [[ $# -ge 2 ]] || desan_die "--suite requires a value"
      SUITE_NAME="$2"
      shift 2
      ;;
    --manifest)
      [[ $# -ge 2 ]] || desan_die "--manifest requires a value"
      MANIFEST="$2"
      shift 2
      ;;
    --runs)
      [[ $# -ge 2 ]] || desan_die "--runs requires a value"
      RUNS_VALUE="$2"
      shift 2
      ;;
    --timeout)
      [[ $# -ge 2 ]] || desan_die "--timeout requires a value"
      TIMEOUT_VALUE="$2"
      shift 2
      ;;
    --no-run)
      RUN_EVAL=0
      shift
      ;;
    --run)
      RUN_EVAL=1
      shift
      ;;
    --output)
      [[ $# -ge 2 ]] || desan_die "--output requires a value"
      OUTPUT_FILE="$2"
      shift 2
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    --)
      shift
      break
      ;;
    -*)
      desan_die "unknown option: $1"
      ;;
    *)
      break
      ;;
  esac
done

TARGET="${1:-}"
if [[ -n "${TARGET}" ]]; then
  shift
fi
CLI_PROGRAM_ARGS=("$@")

if [[ -z "${MANIFEST}" && -z "${TARGET}" ]]; then
  usage
  exit 2
fi

mkdir -p "${DESAN_OUT_DIR}/eval"

SUMMARY_BUFFER=""

append_summary() {
  local line="$1"
  printf '%s\n' "${line}"
  if [[ -n "${OUTPUT_FILE}" ]]; then
    SUMMARY_BUFFER+="${line}"$'\n'
  fi
}

finish_summary() {
  if [[ -n "${OUTPUT_FILE}" ]]; then
    mkdir -p "$(dirname "${OUTPUT_FILE}")"
    printf '%s' "${SUMMARY_BUFFER}" >"${OUTPUT_FILE}"
  fi
}

sanitize_field() {
  local value="$1"
  value="${value//$'\n'/ }"
  value="${value//|/\\|}"
  printf '%s' "${value}"
}

safe_name() {
  printf '%s' "$1" | tr -c 'A-Za-z0-9_.-' '_'
}

sanitizer_display() {
  case "$1" in
    asan | address) echo "ASan" ;;
    ubsan | undefined) echo "UBSan" ;;
    msan | memory) echo "MemSan" ;;
    *) echo "$1" ;;
  esac
}

format_percent() {
  local numerator="$1"
  local denominator="$2"
  awk -v n="${numerator}" -v d="${denominator}" 'BEGIN {
    if (d <= 0) {
      printf "0.0%%";
    } else {
      printf "%.1f%%", (n * 100.0) / d;
    }
  }'
}

format_runtime_overhead() {
  local before="$1"
  local after="$2"
  if [[ "${before}" == "N/A" || "${after}" == "N/A" ]]; then
    echo "N/A"
    return
  fi
  awk -v b="${before}" -v a="${after}" 'BEGIN {
    if (b <= 0) {
      printf "N/A";
    } else {
      printf "%+.1f%%", ((a - b) * 100.0) / b;
    }
  }'
}

core_checks_from_log() {
  local sanitizer="$1"
  local log_file="$2"
  local display
  display="$(sanitizer_display "${sanitizer}")"
  awk -v san="${display}" '
    $1 == san {
      for (i = 1; i <= NF; ++i) {
        if ($i ~ /^count=/) {
          sub(/^count=/, "", $i);
          sum += $i;
        }
      }
    }
    END { print sum + 0 }
  ' "${log_file}" 2>/dev/null
}

removed_checks_from_log() {
  local log_file="$1"
  awk -F': ' '/DESAN Removed Redundant Checks:/ || /DESAN Removed Redundant READ Checks:/ { value=$2 } END { print value + 0 }' "${log_file}" 2>/dev/null
}

classify_detection() {
  local sanitizer="$1"
  local output_file="$2"
  local pattern
  case "${sanitizer}" in
    asan | address)
      pattern='AddressSanitizer|ERROR: AddressSanitizer|heap-buffer|stack-buffer|global-buffer|use-after'
      ;;
    ubsan | undefined)
      pattern='UndefinedBehaviorSanitizer|runtime error:|undefined behavior'
      ;;
    msan | memory)
      pattern='MemorySanitizer|use-of-uninitialized-value|WARNING: MemorySanitizer'
      ;;
    *)
      pattern='Sanitizer|runtime error:'
      ;;
  esac

  if grep -Eiq "${pattern}" "${output_file}" 2>/dev/null; then
    echo "DETECTED"
  else
    echo "CLEAN"
  fi
}

detection_consistency() {
  local expected="$1"
  local before="$2"
  local after="$3"

  if [[ "${before}" == "N/A" || "${after}" == "N/A" ]]; then
    echo "N/A"
    return
  fi

  case "${expected}" in
    yes)
      if [[ "${before}" != "DETECTED" ]]; then
        echo "BASELINE_MISSED"
      elif [[ "${after}" == "DETECTED" ]]; then
        echo "PASS"
      else
        echo "FAIL"
      fi
      ;;
    no)
      if [[ "${before}" == "CLEAN" && "${after}" == "CLEAN" ]]; then
        echo "PASS"
      elif [[ "${before}" == "DETECTED" && "${after}" == "DETECTED" ]]; then
        echo "EXPECTED_CLEAN_BUT_DETECTED"
      else
        echo "FAIL"
      fi
      ;;
    *)
      if [[ "${before}" == "DETECTED" && "${after}" == "DETECTED" ]]; then
        echo "PASS"
      elif [[ "${before}" == "DETECTED" && "${after}" != "DETECTED" ]]; then
        echo "FAIL"
      elif [[ "${before}" == "CLEAN" && "${after}" == "CLEAN" ]]; then
        echo "NO_BUG"
      else
        echo "NEW_DETECTION"
      fi
      ;;
  esac
}

run_timed_binary() {
  local label="$1"
  local sanitizer="$2"
  local binary="$3"
  local log_prefix="$4"
  shift 4

  if [[ "${RUN_EVAL}" != "1" ]]; then
    RUNTIME_RESULT="N/A"
    DETECTION_RESULT="N/A"
    EXIT_RESULT="N/A"
    return
  fi

  local runs="${RUNS_VALUE}"
  local sum="0"
  local count="0"
  local detected="CLEAN"
  local last_status=0
  local timeout_cmd=()
  if [[ -n "${TIMEOUT_VALUE}" ]] && command -v timeout >/dev/null 2>&1; then
    timeout_cmd=("timeout" "${TIMEOUT_VALUE}")
  fi

  local i
  for ((i = 1; i <= runs; ++i)); do
    local stdout_file="${log_prefix}.${label}.${i}.stdout"
    local stderr_file="${log_prefix}.${label}.${i}.stderr"
    local time_file="${log_prefix}.${label}.${i}.time"
    local combined_file="${log_prefix}.${label}.${i}.combined"

    desan_note "running ${label} ${i}/${runs}: ${binary}"
    set +e
    if /usr/bin/time -p -o "${time_file}" "${timeout_cmd[@]}" "${binary}" "$@" >"${stdout_file}" 2>"${stderr_file}"; then
      last_status=0
    else
      last_status=$?
    fi
    set -e

    cat "${stdout_file}" "${stderr_file}" >"${combined_file}"
    if [[ "$(classify_detection "${sanitizer}" "${combined_file}")" == "DETECTED" ]]; then
      detected="DETECTED"
    fi

    local real_time
    real_time="$(awk '/^real / { print $2; exit }' "${time_file}" 2>/dev/null || true)"
    if [[ -n "${real_time}" ]]; then
      sum="$(awk -v s="${sum}" -v r="${real_time}" 'BEGIN { printf "%.9f", s + r }')"
      count=$((count + 1))
    fi
  done

  if [[ "${count}" -gt 0 ]]; then
    RUNTIME_RESULT="$(awk -v s="${sum}" -v c="${count}" 'BEGIN { printf "%.6f", s / c }')"
  else
    RUNTIME_RESULT="N/A"
  fi
  DETECTION_RESULT="${detected}"
  EXIT_RESULT="${last_status}"
}

emit_header() {
  append_summary "| Benchmark | Suite | Sanitizer | Original Checks | Core Checks | Removed Checks | Reduction | Binary Size Before | Binary Size After | Runtime Before | Runtime After | Runtime Overhead | Detection Consistency |"
  append_summary "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|"
}

emit_row() {
  append_summary "| $(sanitize_field "$1") | $(sanitize_field "$2") | $(sanitize_field "$3") | $4 | $5 | $6 | $7 | $8 | $9 | ${10} | ${11} | ${12} | $(sanitize_field "${13}") |"
}

evaluate_one() {
  local suite="$1"
  local benchmark="$2"
  local sanitizer="$3"
  local source="$4"
  local expect_detect="$5"
  shift 5

  [[ -f "${source}" ]] || {
    emit_row "${benchmark}" "${suite}" "$(sanitizer_display "${sanitizer}")" "N/A" "N/A" "N/A" "N/A" "N/A" "N/A" "N/A" "N/A" "N/A" "missing_source"
    return 0
  }

  desan_configure_sanitizer "${sanitizer}"
  local display
  display="$(sanitizer_display "${sanitizer}")"
  local safe_prefix
  safe_prefix="$(safe_name "${suite}_${benchmark}_${SAN_SUFFIX}")"

  local raw_ll="${DESAN_OUT_DIR}/eval/${safe_prefix}.ll"
  local opt_ll="${DESAN_OUT_DIR}/eval/${safe_prefix}_opt.ll"
  local baseline_bin="${DESAN_OUT_DIR}/eval/${safe_prefix}_baseline"
  local opt_bin="${DESAN_OUT_DIR}/eval/${safe_prefix}_opt"
  local pass_log="${DESAN_OUT_DIR}/eval/${safe_prefix}.pass.log"
  local logs_prefix="${DESAN_OUT_DIR}/eval/${safe_prefix}"

  desan_note "evaluating ${suite}/${benchmark} with ${display}"

  if ! desan_make_ir "${SAN_SUFFIX}" "${source}" "${raw_ll}" >/dev/null 2>"${logs_prefix}.emit.log"; then
    emit_row "${benchmark}" "${suite}" "${display}" "N/A" "N/A" "N/A" "N/A" "N/A" "N/A" "N/A" "N/A" "N/A" "emit_ir_failed"
    return 0
  fi

  if ! desan_link_ir "${SAN_SUFFIX}" "${source}" "${raw_ll}" "${baseline_bin}" >/dev/null 2>"${logs_prefix}.baseline_link.log"; then
    emit_row "${benchmark}" "${suite}" "${display}" "N/A" "N/A" "N/A" "N/A" "N/A" "N/A" "N/A" "N/A" "N/A" "baseline_link_failed"
    return 0
  fi

  if ! "${SCRIPT_DIR}/run_pass.sh" "${raw_ll}" "${opt_ll}" \
    -desan-dump-checked-vars=false \
    -desan-dump-check-graphs=false \
    -desan-dump-removals=false \
    >"${pass_log}" 2>&1; then
    emit_row "${benchmark}" "${suite}" "${display}" "N/A" "N/A" "N/A" "N/A" "N/A" "N/A" "N/A" "N/A" "N/A" "pass_failed"
    return 0
  fi

  if ! desan_link_ir "${SAN_SUFFIX}" "${source}" "${opt_ll}" "${opt_bin}" >/dev/null 2>"${logs_prefix}.opt_link.log"; then
    emit_row "${benchmark}" "${suite}" "${display}" "N/A" "N/A" "N/A" "N/A" "N/A" "N/A" "N/A" "N/A" "N/A" "optimized_link_failed"
    return 0
  fi

  local original_checks
  local core_checks
  local removed_checks
  local reduction
  local baseline_size
  local opt_size
  original_checks="$(desan_count_checks "${SAN_SUFFIX}" "${raw_ll}")"
  core_checks="$(core_checks_from_log "${SAN_SUFFIX}" "${pass_log}")"
  removed_checks="$(removed_checks_from_log "${pass_log}")"
  reduction="$(format_percent "${removed_checks}" "${original_checks}")"
  baseline_size="$(wc -c <"${baseline_bin}" | tr -d ' ')"
  opt_size="$(wc -c <"${opt_bin}" | tr -d ' ')"

  run_timed_binary "before" "${SAN_SUFFIX}" "${baseline_bin}" "${logs_prefix}" "$@"
  local runtime_before="${RUNTIME_RESULT}"
  local detect_before="${DETECTION_RESULT}"
  run_timed_binary "after" "${SAN_SUFFIX}" "${opt_bin}" "${logs_prefix}" "$@"
  local runtime_after="${RUNTIME_RESULT}"
  local detect_after="${DETECTION_RESULT}"

  local overhead
  local consistency
  overhead="$(format_runtime_overhead "${runtime_before}" "${runtime_after}")"
  consistency="$(detection_consistency "${expect_detect}" "${detect_before}" "${detect_after}")"

  emit_row "${benchmark}" "${suite}" "${display}" "${original_checks}" "${core_checks}" "${removed_checks}" "${reduction}" "${baseline_size}" "${opt_size}" "${runtime_before}" "${runtime_after}" "${overhead}" "${consistency}"
}

evaluate_benchmark() {
  local suite="$1"
  local benchmark="$2"
  local sanitizer_text="$3"
  local source="$4"
  local expect_detect="$5"
  shift 5

  local sanitizers=()
  if [[ -z "${sanitizer_text}" || "${sanitizer_text}" == "all" ]]; then
    IFS=',' read -r -a sanitizers <<<"${SANITIZER_LIST}"
  else
    IFS=',' read -r -a sanitizers <<<"${sanitizer_text}"
  fi
  for sanitizer in "${sanitizers[@]}"; do
    [[ -n "${sanitizer}" ]] || continue
    evaluate_one "${suite}" "${benchmark}" "${sanitizer}" "${source}" "${expect_detect}" "$@"
  done
}

process_manifest() {
  local manifest="$1"
  [[ -f "${manifest}" ]] || desan_die "manifest does not exist: ${manifest}"
  local manifest_dir
  manifest_dir="$(cd "$(dirname "${manifest}")" && pwd)"

  while IFS= read -r line || [[ -n "${line}" ]]; do
    [[ -n "${line}" ]] || continue
    [[ "${line}" =~ ^[[:space:]]*# ]] && continue

    local suite benchmark sanitizers source args expect_detect
    IFS='|' read -r suite benchmark sanitizers source args expect_detect <<<"${line}"
    suite="${suite:-Unknown}"
    benchmark="${benchmark:-$(basename "${source}")}"
    sanitizers="${sanitizers:-all}"
    args="${args:-}"
    expect_detect="${expect_detect:-auto}"

    if [[ "${source}" != /* ]]; then
      source="${manifest_dir}/${source}"
    fi

    local arg_array=()
    if [[ -n "${args}" ]]; then
      # Manifest args are intentionally simple whitespace-separated fields.
      # Use wrapper scripts for complex quoting or shell expansion.
      read -r -a arg_array <<<"${args}"
    fi
    evaluate_benchmark "${suite}" "${benchmark}" "${sanitizers}" "${source}" "${expect_detect}" "${arg_array[@]}"
  done <"${manifest}"
}

process_target() {
  local target="$1"
  local source
  if [[ -f "${target}" ]]; then
    source="$(desan_abs_path "${target}")"
    local benchmark
    benchmark="$(basename "${source}")"
    benchmark="${benchmark%.*}"
    evaluate_benchmark "${SUITE_NAME}" "${benchmark}" "all" "${source}" "auto" "${CLI_PROGRAM_ARGS[@]}"
  elif [[ -d "${target}" ]]; then
    while IFS= read -r source; do
      [[ -n "${source}" ]] || continue
      local rel benchmark
      rel="${source#${target}/}"
      benchmark="${rel%.*}"
      evaluate_benchmark "${SUITE_NAME}" "${benchmark}" "all" "$(desan_abs_path "${source}")" "auto" "${CLI_PROGRAM_ARGS[@]}"
    done < <(find "${target}" -type f \( -name '*.c' -o -name '*.cc' -o -name '*.cpp' -o -name '*.cxx' -o -name '*.C' \) | sort)
  else
    desan_die "target does not exist: ${target}"
  fi
}

emit_header
if [[ -n "${MANIFEST}" ]]; then
  process_manifest "${MANIFEST}"
else
  process_target "${TARGET}"
fi
finish_summary
