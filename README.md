# DESAN Improved Prototype

This repository provides a streamlined prototype for eliminating redundant
sanitizer checks from C/C++ programs.  The design focuses on clarity and
modularity rather than exhaustive instrumentation.  Each module addresses
one aspect of the pipeline: compilation, alias analysis, sanitizer
detection, dependency graph construction, redundancy analysis, and
orchestration.

## Project layout

```
desan_new/
│   __init__.py
│   compiler.py      # utilities for compiling projects to LLVM bitcode and IR
│   alias_analysis.py # build simple alias and call graphs
│   sanitizer.py     # detect sanitizer runtime calls in IR
│   dependency.py    # derive dependency subgraphs per sanitizer call
│   redundancy.py    # identify redundant checks and prune them from IR
│   pipeline.py      # orchestrates the end‑to‑end flow
└── README.md        # this file
```

### compiler.py

Defines `CompilerConfig` and `Compiler` to gather source files, build
appropriate clang flags for chosen sanitizers, compile sources into
LLVM bitcode (`.bc`), optionally link multiple bitcode files, convert
bitcode into human‑readable IR (`.ll`), and compile IR back into a
binary.  The API can be used standalone or via the pipeline runner.

### alias_analysis.py

Implements a conservative, flow‑insensitive alias analysis and a call
graph.  The `AliasGraph` captures edges induced by pointer assignments
and getelementptr operations.  The `CallGraph` records direct
interprocedural calls.  Helper functions assist in querying alias sets
and checking intersections.

### sanitizer.py

Provides utilities for recognising sanitizer runtime functions and
collecting calls to them in a module.  A `SanitizerCall` object stores
the function, instruction, callee name and operands associated with
each call.

### dependency.py

Using alias information and sanitizer calls, this module builds a
dependency subgraph for every sanitizer invocation.  Each subgraph
records whether any operand is written and the alias sets for each
operand.  These subgraphs are the basis for redundancy analysis.

### redundancy.py

Examines the dependency subgraphs to detect redundant sanitizer checks.
A check is considered redundant if all its operands (and their
aliases) are read‑only and overlap with those of a previous check.
Redundant calls are removed from IR by scanning the textual IR and
skipping the corresponding call instructions.  The resulting IR may
then be compiled back into a binary.

### pipeline.py

Provides a `run_pipeline` function that ties together the modules
above.  It compiles the project, constructs dependency graphs, runs
redundancy analysis, writes out an optimized IR, and compiles it into a
binary.  A simple CLI is available to run the pipeline from the
command line.

## Quick start

1. Install LLVM tools (clang, llvm-link, llvm-dis, opt) and Python
   dependencies (llvmlite).
2. Place the C/C++ project you wish to analyze in a directory.
3. Run the pipeline:

   ```bash
   python -m desan.pipeline --project_path path/to/src \
     --sanitizers asan,ubsan --opt_level O1 --build_dir out --verify
   ```

   This will produce bitcode, IR, optimized IR, and executables under
   the `out` directory.

## Extending the prototype

This project demonstrates a minimal viable framework for reducing
sanitizer overhead.  To improve precision, you may incorporate
additional alias analysis techniques, refine redundancy heuristics, or
integrate with existing build systems.  The modular design should
facilitate experimentation.
