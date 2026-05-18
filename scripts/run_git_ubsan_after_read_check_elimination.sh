#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GIT_SANITIZER=ubsan exec "${SCRIPT_DIR}/run_git_asan_after_read_check_elimination.sh" "$@"
