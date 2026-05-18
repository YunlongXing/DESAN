#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/spec_desan_common.sh"

desan_require_tool "${CLANG_BIN}" "clang"
desan_spec_c_or_cxx "${CLANG_BIN}" "$@"
