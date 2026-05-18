#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

usage() {
  cat >&2 <<'USAGE'
Usage: scripts/build.sh [--clean] [--cmake]

Builds the DESAN LLVM pass plugin.

Environment:
  LLVM_CONFIG   llvm-config executable, e.g. llvm-config-18
  CXX           C++ compiler for the plugin, e.g. clang++
  LLVM_DIR      LLVM CMake package dir when --cmake is used
USAGE
}

clean=0
mode="make"
while (($#)); do
  case "$1" in
    --clean)
      clean=1
      ;;
    --cmake)
      mode="cmake"
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      desan_die "unknown build option: $1"
      ;;
  esac
  shift
done

desan_require_tool "${CLANGXX_BIN}" "clang++"

cd "${DESAN_ROOT}"
if [[ "${mode}" == "cmake" ]]; then
  build_dir="${CMAKE_BUILD_DIR:-${DESAN_ROOT}/cmake-clang-build}"
  if ((clean)); then
    rm -rf "${build_dir}"
  fi

  cmake_args=("-S" "${DESAN_ROOT}" "-B" "${build_dir}" "-DCMAKE_CXX_COMPILER=${CLANGXX_BIN}")
  if [[ -n "${LLVM_DIR:-}" ]]; then
    cmake_args+=("-DLLVM_DIR=${LLVM_DIR}")
  fi

  desan_note "configuring CMake build in ${build_dir}"
  cmake "${cmake_args[@]}"
  desan_note "building DESANPass with CMake"
  cmake --build "${build_dir}"
  echo "${build_dir}/DESANPass.so"
else
  desan_require_tool "${LLVM_CONFIG_BIN}" "llvm-config"
  if ((clean)); then
    make clean
  fi

  desan_note "building DESANPass with Makefile"
  make LLVM_CONFIG="${LLVM_CONFIG_BIN}" CXX="${CLANGXX_BIN}"
  echo "${DESAN_ROOT}/build/DESANPass.so"
fi
