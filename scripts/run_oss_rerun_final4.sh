#!/usr/bin/env bash
set -euo pipefail

cd /home/dragon/DESAN
mkdir -p out
rm -f \
  out/oss-rerun-final-4.status.csv \
  out/oss-rerun-final-4.nohup.log \
  out/oss-rerun-final-4.exit \
  out/oss-rerun-final-4.pid

(
  set +e
  env \
    OSS_STATUS_FILE=out/oss-rerun-final-4.status.csv \
    RUNS=3 \
    OSS_WORKLOAD_LOOPS=3 \
    JOBS=2 \
    OSS_BUILD_TIMEOUT=7200 \
    DESAN_SPEC_PASS_TIMEOUT=300 \
    python3 scripts/run_oss_batch_after_read_check_elimination.py \
      --projects quickjs,giflib,libvpx \
      --sanitizers asan,ubsan,msan \
      --runs 3 \
      --loops 3 \
      --jobs 2 \
      --build-timeout 7200 \
      --run-timeout 300 \
    >out/oss-rerun-final-4.nohup.log 2>&1
  echo "$?" >out/oss-rerun-final-4.exit
) </dev/null &

echo "$!" >out/oss-rerun-final-4.pid
echo "final4:$!"
