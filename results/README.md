# Result Summaries

This directory contains public summary outputs for the DESAN artifact. It does
not contain SPEC CPU source code, inputs, binaries, ISOs, archives, or build
directories.

## Layout

- `desan/all-after-read-check-elimination-results.csv`: curated combined DESAN
  table used for paper-level reporting.
- `desan/spec/`: DESAN summary tables for SPEC CPU 2006 and SPEC CPU 2017.
- `desan/oss/`: DESAN per-project summaries for the curated open-source
  project set in the combined table.
- `asanmm-comparison/`: ASAN-- comparison summaries.
- `sanrazor-comparison/`: SanRazor comparison summaries.

## SanRazor Counting Convention

SanRazor's own `check.txt` files report an internal removed-SC count. In this
artifact, the main SanRazor `*-summary.csv` files use `Detected Disabled` as
`Removed Checks`, meaning the number of UBSan handler paths that are actually
disabled in transformed IR. The original SanRazor reported value is kept as
`SanRazor Reported Removed Checks`.

The SanRazor READ/WRITE/UNKNOWN breakdown is conservative:

- UBSan `type_mismatch_v1` with `TypeCheckKind=0` is READ.
- UBSan `type_mismatch_v1` with `TypeCheckKind=1` is WRITE.
- Arithmetic overflow, shift, pointer overflow, bounds, and ambiguous checks
  are UNKNOWN.
