"""
redundancy.py
-------------

This module defines the logic for detecting redundant sanitizer checks and
rewriting LLVM IR to remove them.  The `RedundancyAnalyzer` works on
subgraphs produced by `SubgraphBuilder`.  Two checks are considered
redundant if they operate on aliasing operands and neither check or its
aliases writes to memory.  The analyzer identifies redundant checks and
provides methods to remove them from textual IR.  Removal uses a simple
heuristic that enumerates sanitizer calls in the order encountered and
skips lines corresponding to redundant call IDs.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Set, Tuple
import subprocess
import os

from .dependency import CheckSubgraph


class RedundancyAnalyzer:
    """Analyze and remove redundant sanitizer checks based on dependency subgraphs."""

    def __init__(self, subgraphs: Dict[str, CheckSubgraph]) -> None:
        self.subgraphs = subgraphs

    def is_redundant_pair(self, key_a: str, key_b: str) -> bool:
        sg_a = self.subgraphs[key_a]
        sg_b = self.subgraphs[key_b]
        # if any operand in either subgraph is written to, keep both
        if any(info.is_write for info in sg_a.details.values()):
            return False
        if any(info.is_write for info in sg_b.details.values()):
            return False
        # check alias intersection: if any alias set overlaps, consider redundant
        for op_a, info_a in sg_a.details.items():
            aliases_a = info_a.alias_set
            for op_b, info_b in sg_b.details.items():
                aliases_b = info_b.alias_set
                if aliases_a & aliases_b:
                    return True
        return False

    def analyze(self) -> Set[str]:
        """Return the set of check keys that are redundant."""
        redundant: Set[str] = set()
        keys = list(self.subgraphs.keys())
        for i in range(len(keys)):
            key_a = keys[i]
            for j in range(i + 1, len(keys)):
                key_b = keys[j]
                if key_b in redundant:
                    continue
                if self.is_redundant_pair(key_a, key_b):
                    redundant.add(key_b)
        return redundant

    def optimize_ir_text(self, ir_text: str, redundant_keys: Set[str]) -> str:
        """Remove redundant sanitizer calls from IR text.

        This function scans the IR line by line, counting sanitizer call
        instructions per function.  When the index (count) matches a
        redundant key, the call line is omitted.  This method does not
        attempt to manipulate IR via llvmlite but works at the text level.
        """
        optimized_lines: List[str] = []
        current_func: str = ""
        call_count: int = 0
        for line in ir_text.splitlines():
            stripped = line.strip()
            if stripped.startswith("define"):
                # update current function name using simple parsing
                parts = stripped.split()
                # find token that starts with '@'
                name = ""
                for tok in parts:
                    if tok.startswith("@"):
                        name = tok.strip()
                        break
                current_func = name
                call_count = 0
                optimized_lines.append(line)
                continue
            # detect sanitizer calls
            if "call" in stripped and any(prefix in stripped for prefix in ("__asan", "__ubsan", "__msan", "__tsan", "__lsan")):
                key = f"{current_func}:call{call_count}"
                call_count += 1
                if key in redundant_keys:
                    # skip this call line
                    continue
            optimized_lines.append(line)
        return "\n".join(optimized_lines)

    def optimize_ir_file(self, ir_path: str, output: str) -> None:
        """Optimize IR file by removing redundant calls and writing to output."""
        if not os.path.exists(ir_path):
            raise FileNotFoundError(ir_path)
        with open(ir_path, "r") as f:
            ir_text = f.read()
        redundant_keys = self.analyze()
        optimized = self.optimize_ir_text(ir_text, redundant_keys)
        with open(output, "w") as f:
            f.write(optimized)

    @staticmethod
    def verify_ir(ir_file: str) -> bool:
        """Run LLVM's verifier on the given IR file."""
        try:
            subprocess.run(["opt", "-verify", ir_file, "-o", "/dev/null"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return True
        except subprocess.CalledProcessError:
            return False