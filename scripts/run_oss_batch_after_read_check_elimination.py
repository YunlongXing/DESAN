#!/usr/bin/env python3
import argparse
import csv
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path("/home/dragon/DESAN")
BENCHMARKS = ROOT / "benchmarks"
OUT_BASE = ROOT / "out"
CC_WRAPPER = ROOT / "scripts" / "spec_desan_cc.sh"
CXX_WRAPPER = ROOT / "scripts" / "spec_desan_cxx.sh"


SANITIZERS = {
    "asan": {
        "base_variant": "asan-base",
        "core_prefixes": [
            "__asan_report_load",
            "__asan_report_store",
            "__asan_load",
            "__asan_store",
        ],
    },
    "ubsan": {
        "base_variant": "ubsan-base",
        "core_prefixes": [
            "__ubsan_handle_type_mismatch",
            "__ubsan_handle_pointer_overflow",
            "__ubsan_handle_out_of_bounds",
            "__ubsan_handle_shift_out_of_bounds",
        ],
    },
    "msan": {
        "base_variant": "msan-base",
        "core_prefixes": [
            "__msan_warning",
            "__msan_maybe_warning",
            "__msan_param_",
            "__msan_retval_",
            "__msan_va_arg_",
            "__msan_check_mem_is_initialized",
            "__msan_test_shadow",
            "__msan_print_shadow",
        ],
    },
}


PROJECTS = {
    "ffmpeg": {
        "repo": "https://github.com/FFmpeg/FFmpeg.git",
        "ref": "n6.1.1",
        "build": './configure --cc="$CC" --cxx="$CXX" --disable-asm --disable-x86asm --disable-doc --disable-debug --disable-network --disable-autodetect --disable-everything --enable-ffmpeg --enable-avcodec --enable-avformat --enable-avfilter --enable-avdevice --enable-swscale --enable-swresample --enable-protocol=file --enable-indev=lavfi --enable-filter=testsrc2 --enable-filter=sine --enable-filter=null --enable-filter=anull --enable-muxer=null --enable-decoder=wrapped_avframe --enable-decoder=pcm_s16le --enable-encoder=wrapped_avframe --enable-encoder=pcm_s16le && make -j"$JOBS" ffmpeg',
        "artifact": "ffmpeg",
        "run": 'for i in $(seq 1 "$LOOPS"); do "$APP" -hide_banner -nostdin -v error -f lavfi -i testsrc2=size=128x128:rate=30:d=1 -f null - >/dev/null; "$APP" -hide_banner -nostdin -v error -f lavfi -i sine=frequency=1000:duration=1 -f null - >/dev/null; done',
    },
    "imagemagick": {
        "repo": "https://github.com/ImageMagick/ImageMagick.git",
        "ref": "7.1.1-38",
        "build": './configure CC="$CC" CXX="$CXX" CFLAGS="$CFLAGS" CXXFLAGS="$CXXFLAGS" --disable-shared --enable-static --disable-openmp --without-bzlib --without-djvu --without-fftw --without-fontconfig --without-freetype --without-gslib --without-heic --without-jbig --without-jpeg --without-lcms --without-lqr --without-lzma --without-openexr --without-pango --without-png --without-raqm --without-tiff --without-webp --without-wmf --without-xml --without-zlib --without-x --without-magick-plus-plus --without-perl && make -j"$JOBS" utilities/magick',
        "artifact": "utilities/magick",
        "run": 'set -e; for i in $(seq 1 "$LOOPS"); do "$APP" "$BENCH/input.ppm" -resize 96x96 -colorspace Gray "$BENCH/out.pgm" >/dev/null; "$APP" identify "$BENCH/out.pgm" >/dev/null; rm -f "$BENCH/out.pgm"; done',
    },
    "zlib": {
        "repo": "https://github.com/madler/zlib.git",
        "ref": "v1.3.1",
        "build": './configure --static && make -j"$JOBS" minigzip',
        "artifact": "minigzip",
        "run": 'for i in $(seq 1 "$LOOPS"); do "$APP" -c "$BENCH/input.txt" >"$BENCH/input.txt.gz"; "$APP" -d -c "$BENCH/input.txt.gz" >/dev/null; rm -f "$BENCH/input.txt.gz"; done',
    },
    "bzip2": {
        "repo": "https://sourceware.org/git/bzip2.git",
        "ref": "bzip2-1.0.8",
        "build": 'make -j"$JOBS" CC="$CC" CFLAGS="$CFLAGS" bzip2',
        "artifact": "bzip2",
        "run": 'for i in $(seq 1 "$LOOPS"); do "$APP" -c "$BENCH/input.txt" >"$BENCH/input.txt.bz2"; "$APP" -d -c "$BENCH/input.txt.bz2" >/dev/null; rm -f "$BENCH/input.txt.bz2"; done',
    },
    "gzip": {
        "archive": "https://ftp.gnu.org/gnu/gzip/gzip-1.13.tar.xz",
        "build": './configure CC="$CC" CFLAGS="$CFLAGS" --disable-nls --disable-dependency-tracking && make -j"$JOBS"',
        "artifact": "gzip",
        "run": 'for i in $(seq 1 "$LOOPS"); do "$APP" -c "$BENCH/input.txt" >"$BENCH/input.txt.gz"; "$APP" -d -c "$BENCH/input.txt.gz" >/dev/null; rm -f "$BENCH/input.txt.gz"; done',
    },
    "xz": {
        "archive": "https://github.com/tukaani-project/xz/releases/download/v5.6.2/xz-5.6.2.tar.xz",
        "build": './configure CC="$CC" CFLAGS="$CFLAGS" --disable-shared --enable-static --disable-nls --disable-scripts && make -j"$JOBS"',
        "artifact": "src/xz/xz",
        "run": 'for i in $(seq 1 "$LOOPS"); do "$APP" -c "$BENCH/input.txt" >/dev/null; done',
    },
    "zstd": {
        "repo": "https://github.com/facebook/zstd.git",
        "ref": "v1.5.6",
        "build": 'make -j"$JOBS" CC="$CC" CFLAGS="$CFLAGS" zstd',
        "artifact": "programs/zstd",
        "run": 'for i in $(seq 1 "$LOOPS"); do "$APP" -q -f "$BENCH/input.txt" -o "$BENCH/input.txt.zst"; "$APP" -q -d -f "$BENCH/input.txt.zst" -c >/dev/null; rm -f "$BENCH/input.txt.zst"; done',
    },
    "lz4": {
        "repo": "https://github.com/lz4/lz4.git",
        "ref": "v1.9.4",
        "build": 'make -j"$JOBS" CC="$CC" CFLAGS="$CFLAGS" lz4',
        "artifact": "programs/lz4",
        "run": 'for i in $(seq 1 "$LOOPS"); do "$APP" -q -f "$BENCH/input.txt" "$BENCH/input.txt.lz4"; "$APP" -q -d -f "$BENCH/input.txt.lz4" -c >/dev/null; rm -f "$BENCH/input.txt.lz4"; done',
    },
    "brotli": {
        "repo": "https://github.com/google/brotli.git",
        "ref": "v1.1.0",
        "build": 'cmake -S . -B build -G Ninja -DCMAKE_C_COMPILER="$CC" -DCMAKE_CXX_COMPILER="$CXX" -DCMAKE_C_FLAGS="$CFLAGS" -DCMAKE_CXX_FLAGS="$CXXFLAGS" -DBUILD_SHARED_LIBS=OFF && cmake --build build --target brotli -j"$JOBS"',
        "artifact": "build/brotli",
        "run": 'for i in $(seq 1 "$LOOPS"); do "$APP" -f "$BENCH/input.txt" -o "$BENCH/input.txt.br"; "$APP" -d -f "$BENCH/input.txt.br" -o "$BENCH/input.txt.out"; rm -f "$BENCH/input.txt.br" "$BENCH/input.txt.out"; done',
    },
    "pigz": {
        "repo": "https://github.com/madler/pigz.git",
        "ref": "v2.8",
        "build": 'make -j"$JOBS" CC="$CC" CFLAGS="$CFLAGS" pigz',
        "artifact": "pigz",
        "run": 'for i in $(seq 1 "$LOOPS"); do "$APP" -c "$BENCH/input.txt" >"$BENCH/input.txt.gz"; "$APP" -d -c "$BENCH/input.txt.gz" >/dev/null; rm -f "$BENCH/input.txt.gz"; done',
    },
    "libdeflate": {
        "repo": "https://github.com/ebiggers/libdeflate.git",
        "ref": "v1.20",
        "build": 'cmake -S . -B build -G Ninja -DCMAKE_C_COMPILER="$CC" -DCMAKE_C_FLAGS="$CFLAGS" -DLIBDEFLATE_BUILD_SHARED_LIB=OFF -DLIBDEFLATE_BUILD_GZIP=ON -DLIBDEFLATE_BUILD_TESTS=OFF && cmake --build build --target libdeflate-gzip -j"$JOBS"',
        "artifact": "build/programs/libdeflate-gzip",
        "run": 'for i in $(seq 1 "$LOOPS"); do "$APP" -c "$BENCH/input.txt" >"$BENCH/input.txt.gz"; "$APP" -d -c "$BENCH/input.txt.gz" >/dev/null; rm -f "$BENCH/input.txt.gz"; done',
    },
    "zopfli": {
        "repo": "https://github.com/google/zopfli.git",
        "ref": "zopfli-1.0.3",
        "build": 'make -j"$JOBS" CC="$CC" CFLAGS="$CFLAGS" zopfli',
        "artifact": "zopfli",
        "run": 'for i in $(seq 1 "$LOOPS"); do "$APP" --gzip -c "$BENCH/small.txt" >"$BENCH/small.txt.gz"; rm -f "$BENCH/small.txt.gz"; done',
    },
    "xxhash": {
        "repo": "https://github.com/Cyan4973/xxHash.git",
        "ref": "v0.8.2",
        "build": 'make -j"$JOBS" CC="$CC" CFLAGS="$CFLAGS" xxhsum',
        "artifact": "xxhsum",
        "run": 'for i in $(seq 1 "$LOOPS"); do "$APP" "$BENCH/input.txt" >/dev/null; done',
    },
    "sqlite": {
        "archive": "https://www.sqlite.org/2024/sqlite-autoconf-3460000.tar.gz",
        "build": './configure CC="$CC" CFLAGS="$CFLAGS" --disable-shared --enable-static --disable-readline && make -j"$JOBS" sqlite3',
        "artifact": "sqlite3",
        "run": 'for i in $(seq 1 "$LOOPS"); do echo "PRAGMA cache_size=1000; CREATE TABLE t(a,b); INSERT INTO t VALUES(1,2),(3,4),(5,6); SELECT sum(a*b) FROM t;" | "$APP" >/dev/null; done',
    },
    "lua": {
        "archive": "https://www.lua.org/ftp/lua-5.4.7.tar.gz",
        "build": 'make -j"$JOBS" linux CC="$CC" MYCFLAGS="$CFLAGS"',
        "artifact": "src/lua",
        "run": 'for i in $(seq 1 "$LOOPS"); do "$APP" "$BENCH/script.lua" >/dev/null; done',
    },
    "quickjs": {
        "archive": "https://bellard.org/quickjs/quickjs-2024-01-13.tar.xz",
        "build": 'ver=$(cat VERSION); make -j"$JOBS" CC="$CC" CONFIG_LTO= CFLAGS_OPT="$CFLAGS -D_GNU_SOURCE -DCONFIG_VERSION=\\\\\\\"$ver\\\\\\\" -DCONFIG_BIGNUM" qjs',
        "artifact": "qjs",
        "run": 'for i in $(seq 1 "$LOOPS"); do "$APP" "$BENCH/script.js" >/dev/null; done',
    },
    "duktape": {
        "archive": "https://duktape.org/duktape-2.7.0.tar.xz",
        "build": 'mkdir -p obj && COMMON="$CFLAGS -pedantic -std=c99 -Wall -fstrict-aliasing -I./examples/cmdline -I./src -DDUK_CMDLINE_PRINTALERT_SUPPORT -I./extras/print-alert -DDUK_CMDLINE_CONSOLE_SUPPORT -I./extras/console -DDUK_CMDLINE_LOGGING_SUPPORT -I./extras/logging -DDUK_CMDLINE_MODULE_SUPPORT -I./extras/module-duktape" && "$CC" $COMMON -c src/duktape.c -o obj/duktape.o && "$CC" $COMMON -c examples/cmdline/duk_cmdline.c -o obj/duk_cmdline.o && "$CC" $COMMON -c extras/print-alert/duk_print_alert.c -o obj/duk_print_alert.o && "$CC" $COMMON -c extras/console/duk_console.c -o obj/duk_console.o && "$CC" $COMMON -c extras/logging/duk_logging.c -o obj/duk_logging.o && "$CC" $COMMON -c extras/module-duktape/duk_module_duktape.c -o obj/duk_module_duktape.o && "$CC" -o duk obj/duktape.o obj/duk_cmdline.o obj/duk_print_alert.o obj/duk_console.o obj/duk_logging.o obj/duk_module_duktape.o -lm',
        "artifact": "duk",
        "run": 'for i in $(seq 1 "$LOOPS"); do "$APP" "$BENCH/script.js" >/dev/null; done',
    },
    "jq": {
        "repo": "https://github.com/jqlang/jq.git",
        "ref": "jq-1.7.1",
        "submodules": True,
        "build": 'autoreconf -fi && ./configure CC="$CC" CFLAGS="$CFLAGS" --disable-shared --enable-static --with-oniguruma=builtin && make -j1 -C modules/oniguruma && make -j1 src/builtin.inc src/config_opts.inc src/version.h && make -j1 jq',
        "artifact": "jq",
        "run": 'for i in $(seq 1 "$LOOPS"); do "$APP" ".items | map(.value) | add" "$BENCH/input.json" >/dev/null; done',
    },
    "grep": {
        "archive": "https://ftp.gnu.org/gnu/grep/grep-3.11.tar.xz",
        "build": './configure CC="$CC" CFLAGS="$CFLAGS" --disable-nls --disable-perl-regexp && make -j"$JOBS"',
        "artifact": "src/grep",
        "run": 'for i in $(seq 1 "$LOOPS"); do "$APP" -E "needle|line" "$BENCH/input.txt" >/dev/null; done',
    },
    "sed": {
        "archive": "https://ftp.gnu.org/gnu/sed/sed-4.9.tar.xz",
        "build": './configure CC="$CC" CFLAGS="$CFLAGS" --disable-nls && make -j"$JOBS" sed/sed',
        "artifact": "sed/sed",
        "run": 'for i in $(seq 1 "$LOOPS"); do "$APP" "s/needle/replaced/g" "$BENCH/input.txt" >/dev/null; done',
    },
    "gawk": {
        "archive": "https://ftp.gnu.org/gnu/gawk/gawk-5.3.0.tar.xz",
        "build": './configure CC="$CC" CFLAGS="$CFLAGS" --disable-nls --without-readline && make -j"$JOBS"',
        "artifact": "gawk",
        "run": 'for i in $(seq 1 "$LOOPS"); do "$APP" "{ s += length($0) } END { print s }" "$BENCH/input.txt" >/dev/null; done',
    },
    "coreutils": {
        "archive": "https://ftp.gnu.org/gnu/coreutils/coreutils-9.5.tar.xz",
        "build": './configure CC="$CC" CFLAGS="$CFLAGS" --disable-nls --enable-no-install-program=stdbuf && make -j"$JOBS"',
        "artifact": "src/wc",
        "run": 'for i in $(seq 1 "$LOOPS"); do "$APP" "$BENCH/input.txt" >/dev/null; "$BUILD/src/sort" "$BENCH/input.txt" >/dev/null; done',
    },
    "findutils": {
        "archive": "https://ftp.gnu.org/gnu/findutils/findutils-4.10.0.tar.xz",
        "build": './configure CC="$CC" CFLAGS="$CFLAGS" --disable-nls && make -j"$JOBS"',
        "artifact": "find/find",
        "run": 'for i in $(seq 1 "$LOOPS"); do "$APP" "$BENCH/tree" -type f -name "*.txt" -print >/dev/null; done',
    },
    "diffutils": {
        "archive": "https://ftp.gnu.org/gnu/diffutils/diffutils-3.10.tar.xz",
        "build": './configure CC="$CC" CFLAGS="$CFLAGS" --disable-nls && make -j"$JOBS"',
        "artifact": "src/diff",
        "run": 'for i in $(seq 1 "$LOOPS"); do "$APP" "$BENCH/input.txt" "$BENCH/input2.txt" >/dev/null || true; done',
    },
    "tar": {
        "archive": "https://ftp.gnu.org/gnu/tar/tar-1.35.tar.xz",
        "build": './configure CC="$CC" CFLAGS="$CFLAGS" --disable-nls && make -j"$JOBS"',
        "artifact": "src/tar",
        "run": 'for i in $(seq 1 "$LOOPS"); do rm -f "$BENCH/archive.tar"; "$APP" -cf "$BENCH/archive.tar" -C "$BENCH/tree" .; "$APP" -tf "$BENCH/archive.tar" >/dev/null; done',
    },
    "m4": {
        "archive": "https://ftp.gnu.org/gnu/m4/m4-1.4.19.tar.xz",
        "build": './configure CC="$CC" CFLAGS="$CFLAGS" --disable-nls && make -j"$JOBS"',
        "artifact": "src/m4",
        "run": 'for i in $(seq 1 "$LOOPS"); do "$APP" "$BENCH/input.m4" >/dev/null; done',
    },
    "make": {
        "archive": "https://ftp.gnu.org/gnu/make/make-4.4.1.tar.gz",
        "build": './configure CC="$CC" CFLAGS="$CFLAGS" --disable-nls && make -j"$JOBS"',
        "artifact": "make",
        "run": 'for i in $(seq 1 "$LOOPS"); do "$APP" -f "$BENCH/Makefile.small" -n >/dev/null; done',
    },
    "busybox": {
        "repo": "https://github.com/mirror/busybox.git",
        "ref": "1_36_1",
        "build": 'make defconfig && sed -i -e "s/^CONFIG_TC=y/# CONFIG_TC is not set/" -e "s/^CONFIG_FEATURE_TC_INGRESS=y/# CONFIG_FEATURE_TC_INGRESS is not set/" .config && yes "" | make oldconfig && make -j"$JOBS" CC="$CC" CFLAGS="$CFLAGS" busybox',
        "artifact": "busybox",
        "run": 'for i in $(seq 1 "$LOOPS"); do "$APP" wc "$BENCH/input.txt" >/dev/null; "$APP" grep needle "$BENCH/input.txt" >/dev/null; done',
    },
    "file": {
        "archive": "https://astron.com/pub/file/file-5.45.tar.gz",
        "build": './configure CC="$CC" CFLAGS="$CFLAGS" --disable-shared --enable-static --disable-libseccomp && make -j"$JOBS"',
        "artifact": "src/file",
        "run": 'for i in $(seq 1 "$LOOPS"); do "$APP" "$BENCH/input.txt" "$BENCH/input.ppm" >/dev/null; done',
    },
    "curl": {
        "archive": "https://curl.se/download/curl-8.8.0.tar.xz",
        "build": './configure CC="$CC" CFLAGS="$CFLAGS" --disable-shared --enable-static --without-ssl --without-zlib --without-brotli --without-zstd --without-libpsl --disable-ldap --disable-ldaps --disable-rtsp --disable-dict --disable-telnet --disable-tftp --disable-pop3 --disable-imap --disable-smtp --disable-gopher --disable-mqtt --disable-manual && make -j"$JOBS"',
        "artifact": "src/curl",
        "run": 'for i in $(seq 1 "$LOOPS"); do "$APP" --version >/dev/null; "$APP" file://"$BENCH/input.txt" >/dev/null; done',
    },
    "wget": {
        "archive": "https://ftp.gnu.org/gnu/wget/wget-1.24.5.tar.gz",
        "build": './configure CC="$CC" CFLAGS="$CFLAGS" --disable-nls --without-ssl --disable-iri --disable-pcre --disable-ntlm --disable-opie --disable-digest && make -j"$JOBS"',
        "artifact": "src/wget",
        "run": 'for i in $(seq 1 "$LOOPS"); do "$APP" --version >/dev/null; done',
    },
    "nginx": {
        "archive": "http://nginx.org/download/nginx-1.26.1.tar.gz",
        "build": './configure --with-cc="$CC" --with-cc-opt="$CFLAGS" --without-http_rewrite_module --without-http_gzip_module --without-pcre --without-mail_pop3_module --without-mail_imap_module --without-mail_smtp_module && make -j"$JOBS"',
        "artifact": "objs/nginx",
        "run": 'for i in $(seq 1 "$LOOPS"); do "$APP" -v >/dev/null 2>&1; done',
    },
    "redis": {
        "repo": "https://github.com/redis/redis.git",
        "ref": "7.2.5",
        "build": 'make -j1 CC="$CC" CFLAGS="$CFLAGS" OPTIMIZATION="-O0" MALLOC=libc BUILD_TLS=no redis-server redis-cli',
        "artifact": "src/redis-server",
        "run": 'for i in $(seq 1 "$LOOPS"); do "$APP" --version >/dev/null; "$BUILD/src/redis-cli" --version >/dev/null; done',
    },
    "c-ares": {
        "repo": "https://github.com/c-ares/c-ares.git",
        "ref": "v1.29.0",
        "build": 'cmake -S . -B build -G Ninja -DCMAKE_C_COMPILER="$CC" -DCMAKE_C_FLAGS="$CFLAGS" -DCARES_SHARED=OFF -DCARES_STATIC=ON -DCARES_BUILD_TESTS=OFF -DCARES_BUILD_TOOLS=ON && cmake --build build -j"$JOBS"',
        "artifact": "build/bin/adig",
        "run": 'for i in $(seq 1 "$LOOPS"); do "$APP" -h >/dev/null 2>&1 || true; done',
    },
    "nghttp2": {
        "archive": "https://github.com/nghttp2/nghttp2/releases/download/v1.62.1/nghttp2-1.62.1.tar.xz",
        "build": './configure CC="$CC" CFLAGS="$CFLAGS" --disable-shared --enable-static --disable-threads --disable-python-bindings --disable-examples --disable-hpack-tools --without-libxml2 --without-jemalloc --without-zlib --without-systemd --without-cunit && make -j"$JOBS"',
        "artifact": "src/nghttp",
        "run": 'for i in $(seq 1 "$LOOPS"); do "$APP" --version >/dev/null; done',
    },
    "libpng": {
        "archive": "https://download.sourceforge.net/libpng/libpng-1.6.43.tar.xz",
        "build": './configure CC="$CC" CFLAGS="$CFLAGS" --disable-shared --enable-static && make -j"$JOBS" pngfix',
        "artifact": "pngfix",
        "run": 'for i in $(seq 1 "$LOOPS"); do "$APP" "$BENCH/input.png" >/dev/null 2>&1 || true; done',
    },
    "libjpeg-turbo": {
        "archive": "https://github.com/libjpeg-turbo/libjpeg-turbo/archive/refs/tags/3.0.3.tar.gz",
        "build": 'cmake -S . -B build -G Ninja -DCMAKE_C_COMPILER="$CC" -DCMAKE_CXX_COMPILER="$CXX" -DCMAKE_C_FLAGS="$CFLAGS" -DCMAKE_CXX_FLAGS="$CXXFLAGS" -DENABLE_SHARED=OFF -DWITH_SIMD=OFF -DWITH_TURBOJPEG=OFF && cmake --build build --target cjpeg-static djpeg-static -j"$JOBS"',
        "artifact": "build/cjpeg-static",
        "run": 'for i in $(seq 1 "$LOOPS"); do "$APP" "$BENCH/input.ppm" >"$BENCH/input.jpg"; "$BUILD/build/djpeg-static" "$BENCH/input.jpg" >/dev/null; rm -f "$BENCH/input.jpg"; done',
    },
    "giflib": {
        "repo": "https://github.com/mirrorer/giflib.git",
        "ref": "",
        "build": 'autoreconf -fi && ./configure CC="$CC" CFLAGS="$CFLAGS" --disable-shared --enable-static && make -j"$JOBS"',
        "artifact": "util/gifbuild",
        "run": 'for i in $(seq 1 "$LOOPS"); do "$APP" -d "$BENCH/input.gif" >"$BENCH/out.gif" 2>/dev/null || true; "$BUILD/util/giftext" "$BENCH/input.gif" >/dev/null 2>&1 || true; rm -f "$BENCH/out.gif"; done',
    },
    "libwebp": {
        "archive": "https://github.com/webmproject/libwebp/archive/refs/tags/v1.4.0.tar.gz",
        "build": 'cmake -S . -B build -G Ninja -DCMAKE_C_COMPILER="$CC" -DCMAKE_CXX_COMPILER="$CXX" -DCMAKE_C_FLAGS="$CFLAGS" -DCMAKE_CXX_FLAGS="$CXXFLAGS" -DWEBP_BUILD_CWEBP=ON -DWEBP_BUILD_DWEBP=ON -DWEBP_BUILD_GIF2WEBP=OFF -DWEBP_BUILD_IMG2WEBP=OFF -DWEBP_BUILD_VWEBP=OFF -DWEBP_BUILD_WEBPINFO=ON -DWEBP_BUILD_WEBPMUX=ON && cmake --build build --target cwebp dwebp -j"$JOBS"',
        "artifact": "build/cwebp",
        "run": 'for i in $(seq 1 "$LOOPS"); do "$APP" -quiet "$BENCH/input.ppm" -o "$BENCH/input.webp"; "$BUILD/build/dwebp" "$BENCH/input.webp" -o "$BENCH/out.ppm" >/dev/null; rm -f "$BENCH/input.webp" "$BENCH/out.ppm"; done',
    },
    "libtiff": {
        "archive": "https://download.osgeo.org/libtiff/tiff-4.6.0.tar.xz",
        "build": 'cmake -S . -B build -G Ninja -DCMAKE_C_COMPILER="$CC" -DCMAKE_CXX_COMPILER="$CXX" -DCMAKE_C_FLAGS="$CFLAGS" -DCMAKE_CXX_FLAGS="$CXXFLAGS" -DBUILD_SHARED_LIBS=OFF -Dtiff-tools=ON -Dtiff-tests=OFF -Dtiff-contrib=OFF -Djbig=OFF -Djpeg=OFF -Dlerc=OFF -Dlibdeflate=OFF -Dlzma=OFF -Dwebp=OFF -Dzstd=OFF && cmake --build build --target tiffinfo -j"$JOBS"',
        "artifact": "build/tools/tiffinfo",
        "run": 'for i in $(seq 1 "$LOOPS"); do "$APP" --version >/dev/null 2>&1 || true; done',
    },
    "flac": {
        "archive": "https://github.com/xiph/flac/archive/refs/tags/1.4.3.tar.gz",
        "build": 'cmake -S . -B build -G Ninja -DCMAKE_C_COMPILER="$CC" -DCMAKE_CXX_COMPILER="$CXX" -DCMAKE_C_FLAGS="$CFLAGS" -DCMAKE_CXX_FLAGS="$CXXFLAGS" -DBUILD_CXXLIBS=OFF -DBUILD_EXAMPLES=OFF -DBUILD_PROGRAMS=ON -DBUILD_TESTING=OFF -DBUILD_SHARED_LIBS=OFF -DINSTALL_MANPAGES=OFF -DWITH_OGG=OFF && cmake --build build --target flac -j"$JOBS"',
        "artifact": "build/src/flac/flac",
        "run": 'for i in $(seq 1 "$LOOPS"); do "$APP" --version >/dev/null; done',
    },
    "x264": {
        "repo": "https://code.videolan.org/videolan/x264.git",
        "ref": "stable",
        "build": './configure --cc="$CC" --disable-asm --enable-static --disable-opencl && make -j"$JOBS" x264',
        "artifact": "x264",
        "run": 'for i in $(seq 1 "$LOOPS"); do "$APP" --version >/dev/null 2>&1; done',
    },
    "libvpx": {
        "archive": "https://github.com/webmproject/libvpx/archive/refs/tags/v1.14.1.tar.gz",
        "build": 'CC="$CC" CXX="$CXX" ./configure --disable-examples --disable-unit-tests --disable-docs --disable-install-docs --disable-optimizations --disable-vp9-highbitdepth --target=generic-gnu && make -j"$JOBS" libvpx.a',
        "artifact": "libvpx.a",
        "run": 'for i in $(seq 1 "$LOOPS"); do test -f "$APP"; done',
    },
    "libxml2": {
        "archive": "https://download.gnome.org/sources/libxml2/2.12/libxml2-2.12.7.tar.xz",
        "build": './configure CC="$CC" CFLAGS="$CFLAGS" --disable-shared --enable-static --without-python --without-lzma --without-zlib --without-iconv && make -j"$JOBS" xmllint',
        "artifact": "xmllint",
        "run": 'for i in $(seq 1 "$LOOPS"); do "$APP" --noout "$BENCH/input.xml" >/dev/null; done',
    },
    "expat": {
        "archive": "https://github.com/libexpat/libexpat/releases/download/R_2_6_2/expat-2.6.2.tar.xz",
        "build": 'cmake -S . -B build -G Ninja -DCMAKE_C_COMPILER="$CC" -DCMAKE_C_FLAGS="$CFLAGS" -DEXPAT_SHARED_LIBS=OFF -DEXPAT_BUILD_TESTS=OFF -DEXPAT_BUILD_TOOLS=ON -DEXPAT_BUILD_EXAMPLES=OFF && cmake --build build --target xmlwf -j"$JOBS"',
        "artifact": "build/xmlwf/xmlwf",
        "run": 'for i in $(seq 1 "$LOOPS"); do "$APP" "$BENCH/input.xml" >/dev/null; done',
    },
    "pcre2": {
        "archive": "https://github.com/PCRE2Project/pcre2/releases/download/pcre2-10.43/pcre2-10.43.tar.gz",
        "build": './configure CC="$CC" CFLAGS="$CFLAGS" --disable-shared --enable-static --disable-jit && make -j"$JOBS" pcre2grep',
        "artifact": "pcre2grep",
        "run": 'for i in $(seq 1 "$LOOPS"); do "$APP" "needle|value" "$BENCH/input.txt" >/dev/null; done',
    },
    "tree-sitter": {
        "repo": "https://github.com/tree-sitter/tree-sitter.git",
        "ref": "v0.22.6",
        "build": 'make -j"$JOBS" CC="$CC" CFLAGS="$CFLAGS" libtree-sitter.a',
        "artifact": "libtree-sitter.a",
        "run": 'for i in $(seq 1 "$LOOPS"); do test -f "$APP"; done',
    },
    "capstone": {
        "repo": "https://github.com/capstone-engine/capstone.git",
        "ref": "5.0.1",
        "build": 'cmake -S . -B build -G Ninja -DCMAKE_C_COMPILER="$CC" -DCMAKE_CXX_COMPILER="$CXX" -DCMAKE_C_FLAGS="$CFLAGS" -DCMAKE_CXX_FLAGS="$CXXFLAGS" -DCAPSTONE_BUILD_SHARED=OFF -DCAPSTONE_BUILD_CSTOOL=ON -DCAPSTONE_BUILD_TESTS=OFF && cmake --build build --target cstool -j"$JOBS"',
        "artifact": "build/cstool",
        "run": 'for i in $(seq 1 "$LOOPS"); do "$APP" x64 "55 48 8b 05 b8 13 00 00" >/dev/null; done',
    },
    "wabt": {
        "repo": "https://github.com/WebAssembly/wabt.git",
        "ref": "1.0.34",
        "submodules": True,
        "build": 'cmake -S . -B build -G Ninja -DCMAKE_C_COMPILER="$CC" -DCMAKE_CXX_COMPILER="$CXX" -DCMAKE_C_FLAGS="$CFLAGS" -DCMAKE_CXX_FLAGS="$CXXFLAGS" -DBUILD_TESTS=OFF && cmake --build build --target wasm-objdump -j"$JOBS"',
        "artifact": "build/wasm-objdump",
        "run": 'for i in $(seq 1 "$LOOPS"); do "$APP" --version >/dev/null; done',
    },
    "libarchive": {
        "archive": "https://github.com/libarchive/libarchive/releases/download/v3.7.4/libarchive-3.7.4.tar.xz",
        "build": './configure CC="$CC" CFLAGS="$CFLAGS" --disable-shared --enable-static --without-bz2lib --without-iconv --without-lz4 --without-lzma --without-lzo2 --without-nettle --without-openssl --without-xml2 --without-zlib --without-zstd && make -j"$JOBS"',
        "artifact": "bsdtar",
        "run": 'for i in $(seq 1 "$LOOPS"); do rm -f "$BENCH/bsd.tar"; "$APP" -cf "$BENCH/bsd.tar" -C "$BENCH/tree" .; "$APP" -tf "$BENCH/bsd.tar" >/dev/null; done',
    },
    "json-c": {
        "archive": "https://github.com/json-c/json-c/archive/refs/tags/json-c-0.17-20230812.tar.gz",
        "build": 'cmake -S . -B build -G Ninja -DCMAKE_C_COMPILER="$CC" -DCMAKE_C_FLAGS="$CFLAGS" -DBUILD_SHARED_LIBS=OFF -DBUILD_TESTING=OFF && cmake --build build -j"$JOBS"',
        "artifact": "build/libjson-c.a",
        "run": 'for i in $(seq 1 "$LOOPS"); do test -f "$APP"; done',
    },
    "cjson": {
        "archive": "https://github.com/DaveGamble/cJSON/archive/refs/tags/v1.7.18.tar.gz",
        "build": 'cmake -S . -B build -G Ninja -DCMAKE_C_COMPILER="$CC" -DCMAKE_C_FLAGS="$CFLAGS" -DBUILD_SHARED_LIBS=OFF -DENABLE_CJSON_TEST=ON -DENABLE_CJSON_UTILS=ON && cmake --build build -j"$JOBS"',
        "artifact": "build/libcjson.a",
        "run": 'for i in $(seq 1 "$LOOPS"); do test -f "$APP"; done',
    },
}


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--projects", default="", help="comma-separated project names")
    parser.add_argument("--sanitizers", default="asan,ubsan,msan")
    parser.add_argument("--runs", type=int, default=int(os.environ.get("RUNS", "3")))
    parser.add_argument("--loops", type=int, default=int(os.environ.get("OSS_WORKLOAD_LOOPS", "3")))
    parser.add_argument("--jobs", type=int, default=int(os.environ.get("JOBS", "2")))
    parser.add_argument("--build-timeout", type=int, default=int(os.environ.get("OSS_BUILD_TIMEOUT", "7200")))
    parser.add_argument("--run-timeout", type=int, default=int(os.environ.get("OSS_RUN_TIMEOUT", "300")))
    parser.add_argument("--continue-on-error", action="store_true", default=True)
    return parser.parse_args()


def sh(cmd, cwd=None, env=None, log=None, timeout=None):
    if log:
        log.write(f"$ {cmd}\n")
        log.flush()
    proc = subprocess.run(
        ["bash", "-lc", cmd],
        cwd=str(cwd) if cwd else None,
        env=env,
        text=True,
        stdout=log or subprocess.PIPE,
        stderr=subprocess.STDOUT if log else subprocess.PIPE,
        timeout=timeout,
    )
    return proc.returncode


def safe_name(name):
    return name.replace("/", "_")


def prepare_archive(name, url, log):
    BENCHMARKS.mkdir(parents=True, exist_ok=True)
    archive_dir = BENCHMARKS / "archives"
    archive_dir.mkdir(parents=True, exist_ok=True)
    suffix = "".join(Path(url).suffixes) or ".tar.gz"
    archive_path = archive_dir / f"{name}{suffix}"
    src_dir = BENCHMARKS / f"{name}-src"
    tmp_dir = BENCHMARKS / f".{name}-extract"
    if not archive_path.exists():
        rc = sh(f'curl -L --retry 3 -o "{archive_path}" "{url}"', cwd=ROOT, log=log, timeout=1800)
        if rc != 0:
            raise RuntimeError(f"download failed for {name}")
    if src_dir.exists():
        shutil.rmtree(src_dir)
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True)
    rc = sh(f'tar -xf "{archive_path}" -C "{tmp_dir}"', cwd=ROOT, log=log, timeout=1800)
    if rc != 0:
        raise RuntimeError(f"extract failed for {name}")
    children = list(tmp_dir.iterdir())
    if len(children) == 1 and children[0].is_dir():
        children[0].rename(src_dir)
        shutil.rmtree(tmp_dir)
    else:
        tmp_dir.rename(src_dir)
    return src_dir


def prepare_git(name, repo, ref, log):
    BENCHMARKS.mkdir(parents=True, exist_ok=True)
    src_dir = BENCHMARKS / f"{name}-src"
    if not (src_dir / ".git").exists():
        if src_dir.exists():
            shutil.rmtree(src_dir)
        cmd = f'git clone --depth 1 --branch "{ref}" "{repo}" "{src_dir}"'
        if sh(cmd, cwd=ROOT, log=log, timeout=1800) != 0:
            if src_dir.exists():
                shutil.rmtree(src_dir)
            rc = sh(f'git clone --depth 1 "{repo}" "{src_dir}"', cwd=ROOT, log=log, timeout=1800)
            if rc != 0:
                raise RuntimeError(f"git clone failed for {name}")
    else:
        if ref:
            sh(f'git -C "{src_dir}" fetch --depth 1 origin "{ref}"', cwd=ROOT, log=log, timeout=1800)
            sh(f'git -C "{src_dir}" checkout -f FETCH_HEAD || git -C "{src_dir}" checkout -f "{ref}"', cwd=ROOT, log=log, timeout=300)
        sh(f'git -C "{src_dir}" clean -fdx', cwd=ROOT, log=log, timeout=600)
    return src_dir


def prepare_source(name, project, log):
    if "archive" in project:
        return prepare_archive(name, project["archive"], log)
    src_dir = prepare_git(name, project["repo"], project.get("ref", ""), log)
    if project.get("submodules"):
        rc = sh(
            f'git -C "{src_dir}" submodule update --init --recursive --depth 1',
            cwd=ROOT,
            log=log,
            timeout=1800,
        )
        if rc != 0:
            raise RuntimeError(f"git submodule update failed for {name}")
    return src_dir


def copy_source(src_dir, build_dir):
    if build_dir.exists():
        shutil.rmtree(build_dir)
    ignore = shutil.ignore_patterns(".git", "__pycache__", ".ninja*", "CMakeFiles")
    shutil.copytree(src_dir, build_dir, ignore=ignore)


def write_bench_inputs(bench):
    bench.mkdir(parents=True, exist_ok=True)
    text = "\n".join(f"line {i:05d} needle value {i % 97}" for i in range(20000)) + "\n"
    (bench / "input.txt").write_text(text)
    (bench / "small.txt").write_text("\n".join(f"short needle {i}" for i in range(100)) + "\n")
    (bench / "input2.txt").write_text(text.replace("needle", "other", 200))
    (bench / "input.json").write_text(
        '{"items":[' + ",".join(f'{{"value":{i},"name":"needle-{i}"}}' for i in range(1000)) + "]}\n"
    )
    (bench / "input.xml").write_text(
        "<root>" + "".join(f'<item id="{i}">needle-{i}</item>' for i in range(1000)) + "</root>\n"
    )
    (bench / "script.lua").write_text("local s=0; for i=1,100000 do s=s+i end; print(s)\n")
    (bench / "script.js").write_text("var s=0; for (var i=0;i<100000;i++) s+=i; print(s);\n")
    (bench / "input.m4").write_text("define(`x', `needle')\nx\n" * 1000)
    (bench / "Makefile.small").write_text("all:\n\t@echo needle\n")
    tree = bench / "tree"
    if tree.exists():
        shutil.rmtree(tree)
    for i in range(50):
        d = tree / f"dir{i % 10}"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"file{i}.txt").write_text(f"needle {i}\n")
    ppm = bench / "input.ppm"
    with ppm.open("w") as f:
        f.write("P3\n128 128\n255\n")
        for y in range(128):
            for x in range(128):
                f.write(f"{x % 256} {y % 256} {(x*y) % 256}\n")
    # Minimal 1x1 transparent GIF.
    (bench / "input.gif").write_bytes(
        bytes.fromhex("47494638396101000100800000000000ffffff21f90401000000002c00000000010001000002024401003b")
    )
    # Minimal PNG, enough for tools that can identify a PNG.
    (bench / "input.png").write_bytes(
        bytes.fromhex(
            "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753de"
            "0000000c49444154789c6360000000020001e221bc330000000049454e44ae426082"
        )
    )


def base_env(sanitizer, disable_pass, out_dir, project_name, jobs):
    env = os.environ.copy()
    env.update(
        {
            "LLVM_CONFIG": env.get("LLVM_CONFIG", "llvm-config-18"),
            "OPT": env.get("OPT", "opt-18"),
            "CLANG": env.get("CLANG", "clang-18"),
            "CLANGXX": env.get("CLANGXX", "clang++-18"),
            "DESAN_LLVM_CONFIG": env.get("DESAN_LLVM_CONFIG", env.get("LLVM_CONFIG", "llvm-config-18")),
            "DESAN_OPT": env.get("DESAN_OPT", env.get("OPT", "opt-18")),
            "DESAN_CLANG": env.get("DESAN_CLANG", env.get("CLANG", "clang-18")),
            "DESAN_CLANGXX": env.get("DESAN_CLANGXX", env.get("CLANGXX", "clang++-18")),
            "PLUGIN": env.get("PLUGIN", str(ROOT / "build" / "DESANPass.so")),
            "DESAN_SPEC_FALLBACK": env.get("DESAN_SPEC_FALLBACK", "1"),
            "DESAN_SPEC_PASS_TIMEOUT": env.get("DESAN_SPEC_PASS_TIMEOUT", "900"),
            "DESAN_SPEC_QUIET": env.get("DESAN_SPEC_QUIET", "1"),
            "DESAN_PASS_ARGS": env.get("DESAN_PASS_ARGS", "-desan-core-top-n=0 -desan-core-min-ratio=0"),
            "ASAN_OPTIONS": env.get("ASAN_OPTIONS", "detect_leaks=0:alloc_dealloc_mismatch=0"),
            "LSAN_OPTIONS": env.get("LSAN_OPTIONS", "detect_leaks=0"),
            "UBSAN_OPTIONS": env.get("UBSAN_OPTIONS", "halt_on_error=0:print_stacktrace=0"),
            "MSAN_OPTIONS": env.get("MSAN_OPTIONS", "halt_on_error=0:exit_code=0:report_umrs=0:print_stats=0"),
            "CC": str(CC_WRAPPER),
            "CXX": str(CXX_WRAPPER),
            "CFLAGS": "-O0 -g -fno-omit-frame-pointer",
            "CXXFLAGS": "-O0 -g -fno-omit-frame-pointer",
            "JOBS": str(jobs),
            "DESAN_OUT_DIR": str(out_dir),
            "DESAN_SPEC_BENCHMARK": project_name,
            "DESAN_SPEC_SANITIZER": sanitizer,
            "DESAN_SPEC_DISABLE_PASS": "1" if disable_pass else "0",
        }
    )
    return env


def build_variant(name, project, src_dir, out_root, label, sanitizer, disable_pass, jobs, log, timeout):
    build_dir = out_root / f"build-{label}"
    copy_source(src_dir, build_dir)
    variant_out = out_root / label
    variant_out.mkdir(parents=True, exist_ok=True)
    env = base_env(sanitizer, disable_pass, variant_out, name, jobs)
    log.write(f"=== {name} {label} build ===\n")
    rc = sh(project["build"], cwd=build_dir, env=env, log=log, timeout=timeout)
    if rc != 0:
        raise RuntimeError(f"{name} {label} build failed with {rc}")
    log.write(f"=== {name} {label} build done ===\n")
    return build_dir


def run_runtime(name, project, out_root, label, build_dir, bench, runs, loops, timeout, csv_writer, log):
    artifact = project.get("artifact", "")
    app = build_dir / artifact if artifact else build_dir
    command = project.get("run", "")
    if artifact and not app.exists():
        log.write(f"missing artifact for {name} {label}: {app}\n")
        for run in range(1, runs + 1):
            csv_writer.writerow([label, run, "NR", ""])
        return
    env = os.environ.copy()
    env.update(
        {
            "APP": str(app),
            "BUILD": str(build_dir),
            "BENCH": str(bench),
            "LOOPS": str(loops),
            "ASAN_OPTIONS": env.get("ASAN_OPTIONS", "detect_leaks=0:alloc_dealloc_mismatch=0"),
            "LSAN_OPTIONS": env.get("LSAN_OPTIONS", "detect_leaks=0"),
            "UBSAN_OPTIONS": env.get("UBSAN_OPTIONS", "halt_on_error=0:print_stacktrace=0"),
            "MSAN_OPTIONS": env.get("MSAN_OPTIONS", "halt_on_error=0:exit_code=0:report_umrs=0:print_stats=0"),
        }
    )
    for run in range(1, runs + 1):
        start = time.perf_counter()
        try:
            rc = sh(f"set -e; {command}", cwd=build_dir, env=env, log=log, timeout=timeout)
        except subprocess.TimeoutExpired:
            rc = 124
        elapsed = time.perf_counter() - start
        csv_writer.writerow([label, run, "S" if rc == 0 else "RE", f"{elapsed:.6f}"])


def summarize(name, sanitizer, out_root):
    san = SANITIZERS[sanitizer]
    summary_md = OUT_BASE / f"{name}-{sanitizer}-after-read-check-elimination-summary.md"
    summary_csv = OUT_BASE / f"{name}-{sanitizer}-after-read-check-elimination-summary.csv"
    records = out_root / "desan" / "spec-logs" / "compile_records.tsv"
    runtime_csv = out_root / "runtime.csv"
    cmd = [
        "python3",
        str(ROOT / "scripts" / "opensource_summary.py"),
        "--suite",
        "OpenSource",
        "--benchmark",
        name,
        "--records",
        str(records),
        "--runtime-csv",
        str(runtime_csv),
        "--before-variant",
        san["base_variant"],
        "--after-variant",
        "desan",
        "--csv-out",
        str(summary_csv),
    ]
    for prefix in san["core_prefixes"]:
        cmd.extend(["--core-prefix", prefix])
    with summary_md.open("w") as out:
        subprocess.run(cmd, cwd=str(ROOT), stdout=out, stderr=subprocess.STDOUT, check=False)


def run_one(name, sanitizer, args, aggregate_writer):
    project = PROJECTS[name]
    out_root = OUT_BASE / f"{name}-{sanitizer}-after-read-check-elimination"
    log_path = OUT_BASE / f"{name}_{sanitizer}_after_read_check_elimination.nohup.log"
    summary_status = "S"
    message = ""
    if out_root.exists():
        shutil.rmtree(out_root)
    for suffix in ("summary.md", "summary.csv"):
        p = OUT_BASE / f"{name}-{sanitizer}-after-read-check-elimination-{suffix}"
        if p.exists():
            p.unlink()
    out_root.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", buffering=1) as log:
        try:
            src_dir = prepare_source(name, project, log)
            bench = out_root / "bench"
            write_bench_inputs(bench)
            native_dir = build_variant(name, project, src_dir, out_root, "native", "none", True, args.jobs, log, args.build_timeout)
            base_label = SANITIZERS[sanitizer]["base_variant"]
            base_dir = build_variant(name, project, src_dir, out_root, base_label, sanitizer, True, args.jobs, log, args.build_timeout)
            desan_dir = build_variant(name, project, src_dir, out_root, "desan", sanitizer, False, args.jobs, log, args.build_timeout)
            runtime_csv = out_root / "runtime.csv"
            with runtime_csv.open("w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["Variant", "Run", "Status", "Seconds"])
                run_runtime(name, project, out_root, "native", native_dir, bench, args.runs, args.loops, args.run_timeout, writer, log)
                run_runtime(name, project, out_root, base_label, base_dir, bench, args.runs, args.loops, args.run_timeout, writer, log)
                run_runtime(name, project, out_root, "desan", desan_dir, bench, args.runs, args.loops, args.run_timeout, writer, log)
            summarize(name, sanitizer, out_root)
        except Exception as exc:  # keep the batch moving
            summary_status = "FAIL"
            message = str(exc)
            log.write(f"FAILED: {message}\n")
    aggregate_writer.writerow([name, sanitizer, summary_status, message])


def main():
    args = parse_args()
    if args.projects:
        projects = [p.strip() for p in args.projects.split(",") if p.strip()]
    else:
        projects = list(PROJECTS)
    sanitizers = [s.strip() for s in args.sanitizers.split(",") if s.strip()]
    for p in projects:
        if p not in PROJECTS:
            raise SystemExit(f"unknown project: {p}")
    for s in sanitizers:
        if s not in SANITIZERS:
            raise SystemExit(f"unknown sanitizer: {s}")

    OUT_BASE.mkdir(parents=True, exist_ok=True)
    aggregate = Path(
        os.environ.get(
            "OSS_STATUS_FILE",
            str(OUT_BASE / "oss-batch-after-read-check-elimination-status.csv"),
        )
    )
    write_header = not aggregate.exists()
    with aggregate.open("a", newline="") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(["Project", "Sanitizer", "Status", "Message"])
        for project in projects:
            for sanitizer in sanitizers:
                print(f"=== {project} {sanitizer} ===", flush=True)
                run_one(project, sanitizer, args, writer)
                f.flush()


if __name__ == "__main__":
    main()
