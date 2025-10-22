"""
pipeline.py
-----------

High‑level orchestrator that stitches together the various components of
the DESAN prototype.  The pipeline performs the following tasks in order:

1. Compile the target project to LLVM bitcode with the selected sanitizers.
2. Convert the bitcode to textual IR.
3. Build alias and dependency graphs for sanitizer calls.
4. Analyze redundancy among checks and remove unnecessary ones.
5. Recompile the optimized IR to produce an executable binary.

This module exposes a `run_pipeline` function as well as a CLI via the
`main` function.  The CLI accepts the usual arguments such as project
path, sanitizers, optimization level, build directory, and a flag to
verify the intermediate IR.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Optional

from .compiler import Compiler, CompilerConfig
from .alias_analysis import parse_bitcode
from .dependency import SubgraphBuilder
from .redundancy import RedundancyAnalyzer


def run_pipeline(
    project_path: str,
    sanitizers: str = "asan",
    opt_level: str = "O0",
    build_dir: str = "build",
    verify: bool = False,
    include_cpp: bool = True,
    defines: str = "",
    include_paths: str = "",
    extra_flags: str = "",
) -> Dict[str, str]:
    """Execute the full DESAN pipeline and return output file paths.

    Returns a mapping of stage names to file paths: bitcode, ir, optimized_ir,
    and binary.
    """
    config = CompilerConfig(
        project_path=project_path,
        sanitizers=[s.strip() for s in sanitizers.split(',') if s.strip()],
        opt_level=opt_level,
        include_cpp=include_cpp,
        defines=[d for d in defines.split(',') if d],
        include_paths=[p for p in include_paths.split(':') if p],
        extra_flags=[f for f in extra_flags.split(',') if f],
    )
    compiler = Compiler(config)
    bc_file, ir_file, bin_file = compiler.run(build_dir=build_dir, split=False, verify=verify)
    # build subgraphs for sanitizer calls
    module = parse_bitcode(bc_file)
    builder = SubgraphBuilder(module)
    subgraphs = builder.build_all()
    # analyze redundancy and generate optimized IR
    analyzer = RedundancyAnalyzer(subgraphs)
    optimized_ir = Path(build_dir) / "program_optimized.ll"
    analyzer.optimize_ir_file(ir_file, str(optimized_ir))
    # optionally verify optimized IR
    if verify:
        if not analyzer.verify_ir(str(optimized_ir)):
            raise RuntimeError("Verification of optimized IR failed")
    # compile optimized IR to binary
    optimized_bin = Path(build_dir) / "program_optimized"
    compiler.compile_ir(str(optimized_ir), str(optimized_bin))
    return {
        "bitcode": bc_file,
        "ir": ir_file,
        "optimized_ir": str(optimized_ir),
        "binary": str(optimized_bin),
    }


def parse_cli(args: Optional[Iterable[str]] = None):
    import argparse
    parser = argparse.ArgumentParser(description="Run the DESAN pipeline on a C/C++ project")
    parser.add_argument("--project_path", required=True, help="Path to the source project")
    parser.add_argument("--sanitizers", default="asan", help="Comma-separated sanitizers to enable")
    parser.add_argument("--opt_level", default="O0", help="Optimization level for clang")
    parser.add_argument("--build_dir", default="build", help="Output directory for intermediate and final files")
    parser.add_argument("--verify", action="store_true", help="Verify intermediate and optimized IR")
    parser.add_argument("--include_cpp", action="store_true", help="Compile C++ sources as well")
    parser.add_argument("--defines", default="", help="Comma-separated preprocessor defines")
    parser.add_argument("--include_paths", default="", help="Colon-separated include directories")
    parser.add_argument("--extra_flags", default="", help="Additional flags for clang")
    return parser.parse_args(args)


def main():
    args = parse_cli()
    outputs = run_pipeline(
        project_path=args.project_path,
        sanitizers=args.sanitizers,
        opt_level=args.opt_level,
        build_dir=args.build_dir,
        verify=args.verify,
        include_cpp=args.include_cpp,
        defines=args.defines,
        include_paths=args.include_paths,
        extra_flags=args.extra_flags,
    )
    print("Pipeline completed. Outputs:")
    for k, v in outputs.items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    main()