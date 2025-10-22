"""
compiler.py
------------

This module wraps the clang/LLVM toolchain to compile C and C++ projects
into LLVM bitcode and textual IR with selected sanitizers enabled.  The
functions defined here aim to provide a flexible API for discovering source
files, assembling compiler flags, invoking clang, converting bitcode to
human‑readable IR, and linking multiple bitcode files when necessary.

The API is centred around two constructs: `CompilerConfig`, a simple data
container that specifies the key compilation parameters, and `Compiler`,
which exposes high‑level methods to perform the compilation steps.  Most
methods accept optional parameters to override default behaviour; this
makes the interface suitable for integration into larger systems or CI
pipelines where build configurations may vary per project.

Note that this implementation intentionally avoids heavy reliance on
external build systems.  It performs a basic recursive search to gather
all `.c` and `.cpp` files under the project directory.  For more
complex projects that use Make, CMake or other build tools, you may
prefer to instrument the original build rather than rely on file
discovery.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence, Tuple


@dataclass
class CompilerConfig:
    """Configuration for compiling a project into LLVM IR.

    Attributes:
        project_path: Root directory containing C/C++ source files.
        sanitizers: Sanitizers to enable, such as "asan", "ubsan", "msan".
        opt_level: Optimization level string, e.g. "O0", "O1", etc.
        include_cpp: Whether to include C++ sources.
        defines: List of preprocessor definitions to pass to clang.
        include_paths: List of include directories.
        extra_flags: Additional compiler flags.
    """

    project_path: str
    sanitizers: Sequence[str] = field(default_factory=list)
    opt_level: str = "O0"
    include_cpp: bool = True
    defines: Sequence[str] = field(default_factory=list)
    include_paths: Sequence[str] = field(default_factory=list)
    extra_flags: Sequence[str] = field(default_factory=list)

    def sanitize_flags(self) -> List[str]:
        """Build a list of sanitizer flags for clang based on the config."""
        mapping = {
            "asan": "-fsanitize=address",
            "ubsan": "-fsanitize=undefined",
            "msan": "-fsanitize=memory",
            "tsan": "-fsanitize=thread",
            "lsan": "-fsanitize=leak",
        }
        flags: List[str] = []
        for s in self.sanitizers:
            flag = mapping.get(s)
            if flag and flag not in flags:
                flags.append(flag)
        return flags

    def optimization_flag(self) -> str:
        lvl = self.opt_level.strip()
        return f"-{lvl}" if lvl.startswith("O") else "-O0"

    def define_flags(self) -> List[str]:
        return [f"-D{d}" for d in self.defines]

    def include_flags(self) -> List[str]:
        return [f"-I{p}" for p in self.include_paths]

    def extra(self) -> List[str]:
        return list(self.extra_flags)


class Compiler:
    """High‑level compiler wrapper for building LLVM bitcode and IR."""

    def __init__(self, config: CompilerConfig) -> None:
        self.config = config

    def discover_sources(self) -> Tuple[List[str], List[str]]:
        """Discover C and optionally C++ source files under the project path."""
        c_files: List[str] = []
        cpp_files: List[str] = []
        for root, _, files in os.walk(self.config.project_path):
            for fname in files:
                if fname.endswith(".c"):
                    c_files.append(os.path.join(root, fname))
                elif self.config.include_cpp and fname.endswith((".cpp", ".cc", ".cxx")):
                    cpp_files.append(os.path.join(root, fname))
        return c_files, cpp_files

    def build_flags(self) -> List[str]:
        """Assemble clang flags based on configuration."""
        flags = []
        flags.extend(self.config.sanitize_flags())
        flags.append(self.config.optimization_flag())
        flags.append("-emit-llvm")
        flags.append("-c")
        flags.extend(self.config.define_flags())
        flags.extend(self.config.include_flags())
        flags.extend(self.config.extra())
        return flags

    def compile_to_bitcode(self, output: str) -> str:
        """Compile discovered sources into a single LLVM bitcode file."""
        c_files, cpp_files = self.discover_sources()
        sources = c_files + cpp_files
        if not sources:
            raise RuntimeError(f"No source files found in {self.config.project_path}")
        flags = self.build_flags()
        output_path = Path(output).with_suffix(".bc").resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = ["clang"]
        cmd.extend(flags)
        cmd.extend(sources)
        cmd.extend(["-o", str(output_path)])
        # run clang
        subprocess.run(cmd, check=True)
        return str(output_path)

    def compile_individual(self, sources: Sequence[str], output_dir: str) -> List[str]:
        """Compile each source into its own bitcode file and return their paths."""
        bc_files: List[str] = []
        flags = self.build_flags()
        for src in sources:
            name = Path(src).stem
            out = Path(output_dir) / f"{name}.bc"
            out.parent.mkdir(parents=True, exist_ok=True)
            cmd = ["clang"]
            cmd.extend(flags)
            cmd.append(src)
            cmd.extend(["-o", str(out)])
            subprocess.run(cmd, check=True)
            bc_files.append(str(out))
        return bc_files

    def link_bitcode(self, files: Sequence[str], output: str) -> str:
        """Link multiple bitcode files into a single bitcode using llvm-link."""
        if not files:
            raise RuntimeError("No bitcode files provided for linking")
        output_path = Path(output).with_suffix(".bc").resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = ["llvm-link"]
        cmd.extend(files)
        cmd.extend(["-o", str(output_path)])
        subprocess.run(cmd, check=True)
        return str(output_path)

    def to_text_ir(self, bc_file: str, output: Optional[str] = None) -> str:
        """Convert bitcode to textual LLVM IR using llvm-dis."""
        bc_path = Path(bc_file)
        if not bc_path.exists():
            raise FileNotFoundError(bc_file)
        ll_path = Path(output) if output else bc_path.with_suffix(".ll")
        ll_path = ll_path.resolve()
        ll_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = ["llvm-dis", str(bc_path), "-o", str(ll_path)]
        subprocess.run(cmd, check=True)
        return str(ll_path)

    def compile_ir(self, ir_file: str, output: str, link_flags: Optional[Sequence[str]] = None) -> str:
        """Compile textual IR into a binary using clang."""
        if not os.path.exists(ir_file):
            raise FileNotFoundError(ir_file)
        output_path = Path(output).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = ["clang", ir_file, "-o", str(output_path)]
        if link_flags:
            cmd.extend(link_flags)
        subprocess.run(cmd, check=True)
        return str(output_path)

    def run(self, build_dir: str, split: bool = False, verify: bool = False) -> Tuple[str, str, str]:
        """Execute the complete compile pipeline.

        Args:
            build_dir: directory where intermediate and final files will reside.
            split: compile each source separately and link them.
            verify: if True, run opt -verify on the generated IR.

        Returns:
            Tuple of (bitcode_path, ir_path, binary_path).
        """
        build_path = Path(build_dir).resolve()
        build_path.mkdir(parents=True, exist_ok=True)
        if split:
            c_files, cpp_files = self.discover_sources()
            sources = c_files + cpp_files
            tmp_bc = self.compile_individual(sources, os.path.join(build_dir, "objs"))
            bc_file = self.link_bitcode(tmp_bc, os.path.join(build_dir, "program.bc"))
        else:
            bc_file = self.compile_to_bitcode(os.path.join(build_dir, "program.bc"))
        ll_file = self.to_text_ir(bc_file, os.path.join(build_dir, "program.ll"))
        if verify:
            # run opt -verify to check IR validity
            try:
                subprocess.run(["opt", "-verify", ll_file, "-o", "/dev/null"], check=True)
            except subprocess.CalledProcessError as e:
                raise RuntimeError(f"IR verification failed: {e.stderr}")
        bin_file = self.compile_ir(ll_file, os.path.join(build_dir, "program"))
        return bc_file, ll_file, bin_file

    @staticmethod
    def parse_args(args: Optional[Sequence[str]] = None) -> CompilerConfig:
        import argparse
        parser = argparse.ArgumentParser(description="Compile a project to LLVM IR with sanitizers.")
        parser.add_argument("--project_path", required=True, help="Path to project sources")
        parser.add_argument("--sanitizers", default="asan", help="Comma-separated sanitizers")
        parser.add_argument("--opt_level", default="O0", help="Optimization level")
        parser.add_argument("--include_cpp", action="store_true", help="Include C++ files")
        parser.add_argument("--defines", default="", help="Comma-separated preprocessor defines")
        parser.add_argument("--include_paths", default="", help="Colon-separated include paths")
        parser.add_argument("--extra_flags", default="", help="Additional flags for clang")
        args_ns = parser.parse_args(args)
        sanitizers = [s.strip() for s in args_ns.sanitizers.split(',') if s.strip()]
        defines = [d for d in args_ns.defines.split(',') if d]
        include_paths = [p for p in args_ns.include_paths.split(':') if p]
        extra_flags = [f for f in args_ns.extra_flags.split(',') if f]
        return CompilerConfig(
            project_path=args_ns.project_path,
            sanitizers=sanitizers,
            opt_level=args_ns.opt_level,
            include_cpp=args_ns.include_cpp,
            defines=defines,
            include_paths=include_paths,
            extra_flags=extra_flags,
        )

    @staticmethod
    def main() -> None:
        config = Compiler.parse_args()
        compiler = Compiler(config)
        compiler.run(build_dir="build", split=False)

if __name__ == "__main__":
    Compiler.main()