#!/usr/bin/env bash
set -euo pipefail

cd /home/dragon/DESAN

PROJECTS='ffmpeg,imagemagick,zlib,bzip2,gzip,xz,zstd,lz4,brotli,pigz,libdeflate,zopfli,xxhash,sqlite,lua,quickjs,duktape,jq,grep,sed,gawk,coreutils,findutils,diffutils,tar,m4,make,busybox,file,curl,wget,nginx,redis,c-ares,nghttp2,libpng,libjpeg-turbo,giflib,libwebp,libtiff,flac,x264,libvpx,libxml2,expat,pcre2,tree-sitter,capstone,wabt,libarchive,json-c,cjson'

python3 - <<'PY'
import csv
import glob
from pathlib import Path

sources = []
for pattern in [
    "out/oss-batch-after-read-check-elimination-status.csv",
    "out/oss-extra50-shard-*.status.csv",
    "out/oss-rerun-fixes-*.status.csv",
    "out/oss-rerun-final-*.status.csv",
    "out/oss-rerun-zz-*.status.csv",
]:
    sources.extend(sorted(glob.glob(pattern)))

fieldnames = ["Project", "Sanitizer", "Status", "Message"]
rows = {}
order = []
for source in sources:
    path = Path(source)
    if not path.exists():
        continue
    with path.open(newline="", errors="replace") as f:
        for row in csv.DictReader(f):
            key = (row.get("Project", ""), row.get("Sanitizer", ""))
            if not key[0] or not key[1]:
                continue
            if key not in rows:
                order.append(key)
            rows[key] = {name: row.get(name, "") for name in fieldnames}

out = Path("out/oss-all-after-read-check-elimination-status.csv")
with out.open("w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    for key in order:
        writer.writerow(rows[key])
PY

cp out/oss-all-after-read-check-elimination-status.csv \
  out/oss-batch-after-read-check-elimination-status.csv

scripts/collect_oss_batch_results.py \
  --projects "${PROJECTS}" \
  --sanitizers asan,ubsan,msan \
  --csv-out out/oss-all-after-read-check-elimination-results.csv \
  --md-out out/oss-all-after-read-check-elimination-results.md

echo '--- failures ---'
awk -F, 'NR > 1 && $3 != "S" {print}' \
  out/oss-all-after-read-check-elimination-status.csv

echo '--- result head ---'
head -5 out/oss-all-after-read-check-elimination-results.md
echo '--- result tail ---'
tail -20 out/oss-all-after-read-check-elimination-results.md
