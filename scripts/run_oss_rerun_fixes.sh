#!/usr/bin/env bash
set -euo pipefail

cd /home/dragon/DESAN
mkdir -p out

rm -f \
  out/oss-rerun-fixes-1.status.csv \
  out/oss-rerun-fixes-2.status.csv \
  out/oss-rerun-fixes-1.nohup.log \
  out/oss-rerun-fixes-2.nohup.log \
  out/oss-rerun-fixes-1.exit \
  out/oss-rerun-fixes-2.exit \
  out/oss-rerun-fixes-1.pid \
  out/oss-rerun-fixes-2.pid

run_shard() {
  local id="$1"
  local projects="$2"
  (
    set +e
    env \
      OSS_STATUS_FILE="out/oss-rerun-fixes-${id}.status.csv" \
      RUNS=3 \
      OSS_WORKLOAD_LOOPS=3 \
      JOBS=2 \
      OSS_BUILD_TIMEOUT=7200 \
      DESAN_SPEC_PASS_TIMEOUT=300 \
      python3 scripts/run_oss_batch_after_read_check_elimination.py \
        --projects "${projects}" \
        --sanitizers asan,ubsan,msan \
        --runs 3 \
        --loops 3 \
        --jobs 2 \
        --build-timeout 7200 \
        --run-timeout 300 \
      >"out/oss-rerun-fixes-${id}.nohup.log" 2>&1
    echo "$?" >"out/oss-rerun-fixes-${id}.exit"
  ) </dev/null &
  echo "$!" >"out/oss-rerun-fixes-${id}.pid"
  echo "shard${id}:$!"
}

run_shard 1 "gzip,xz,quickjs,jq,grep,gawk,coreutils,findutils,diffutils,tar,m4,make,busybox,file,curl,wget"
run_shard 2 "redis,libjpeg-turbo,giflib,libtiff,flac,libvpx,tree-sitter,wabt,libarchive,json-c,cjson"
