#!/usr/bin/env bash
set -euo pipefail

cd /home/dragon/DESAN
mkdir -p out

rm -f \
  out/oss-rerun-final-1.status.csv \
  out/oss-rerun-final-2.status.csv \
  out/oss-rerun-final-3.status.csv \
  out/oss-rerun-final-1.nohup.log \
  out/oss-rerun-final-2.nohup.log \
  out/oss-rerun-final-3.nohup.log \
  out/oss-rerun-final-1.exit \
  out/oss-rerun-final-2.exit \
  out/oss-rerun-final-3.exit \
  out/oss-rerun-final-1.pid \
  out/oss-rerun-final-2.pid \
  out/oss-rerun-final-3.pid

run_shard() {
  local id="$1"
  local projects="$2"
  local sanitizers="$3"
  (
    set +e
    env \
      OSS_STATUS_FILE="out/oss-rerun-final-${id}.status.csv" \
      RUNS=3 \
      OSS_WORKLOAD_LOOPS=3 \
      JOBS=2 \
      OSS_BUILD_TIMEOUT=7200 \
      DESAN_SPEC_PASS_TIMEOUT=300 \
      python3 scripts/run_oss_batch_after_read_check_elimination.py \
        --projects "${projects}" \
        --sanitizers "${sanitizers}" \
        --runs 3 \
        --loops 3 \
        --jobs 2 \
        --build-timeout 7200 \
        --run-timeout 300 \
      >"out/oss-rerun-final-${id}.nohup.log" 2>&1
    echo "$?" >"out/oss-rerun-final-${id}.exit"
  ) </dev/null &
  echo "$!" >"out/oss-rerun-final-${id}.pid"
  echo "final${id}:$!"
}

run_shard 1 "quickjs,jq,busybox,xz" "asan,ubsan,msan"
run_shard 2 "giflib,libvpx" "asan,ubsan,msan"
run_shard 3 "redis" "asan"
