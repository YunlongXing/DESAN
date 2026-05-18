#!/usr/bin/env bash
set -euo pipefail

cd /home/dragon/DESAN

chmod +x scripts/run_oss_batch_after_read_check_elimination.py \
  scripts/collect_oss_batch_results.py

rm -f out/oss-extra50-shard-*.status.csv out/oss-extra50-shard-*.driver.log

P1='zlib,bzip2,gzip,xz,zstd,lz4,brotli,pigz,libdeflate,zopfli,xxhash,sqlite,lua,quickjs'
P2='duktape,jq,grep,sed,gawk,coreutils,findutils,diffutils,tar,m4,make,busybox,file'
P3='curl,wget,nginx,redis,c-ares,nghttp2,libpng,libjpeg-turbo,giflib,libwebp,libtiff,flac,x264'
P4='libvpx,libxml2,expat,pcre2,tree-sitter,capstone,wabt,libarchive,json-c,cjson'

run_shard() {
  local shard="$1"
  local projects="$2"
  OSS_STATUS_FILE="out/oss-extra50-shard-${shard}.status.csv" \
  RUNS=3 \
  OSS_WORKLOAD_LOOPS=3 \
  JOBS=2 \
  OSS_BUILD_TIMEOUT=7200 \
  DESAN_SPEC_PASS_TIMEOUT=300 \
    scripts/run_oss_batch_after_read_check_elimination.py \
      --projects "${projects}" \
      --sanitizers asan,ubsan,msan \
      --runs 3 \
      --loops 3 \
      --jobs 2 \
      --build-timeout 7200 \
      --run-timeout 300 \
      >"out/oss-extra50-shard-${shard}.driver.log" 2>&1
  echo "shard${shard}_done"
}

run_shard 1 "${P1}" &
run_shard 2 "${P2}" &
run_shard 3 "${P3}" &
run_shard 4 "${P4}" &

wait
echo all_extra50_done
