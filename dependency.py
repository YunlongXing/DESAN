"""
dependency.py
-------------

The dependency builder constructs per‑check dependency graphs that combine
sanitizer calls with alias information obtained from the alias analysis.
Each subgraph records the function and instruction where the sanitizer is
invoked, the operands of the call, whether any operand or its aliases
represent a write, and the full alias set for each operand.  These
subgraphs serve as the input for redundancy analysis.  The `SubgraphBuilder`
class encapsulates this logic, given an LLVM module and an alias graph.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple
from llvmlite import binding as llvm

from .alias_analysis import AliasGraph, Pointer, build_alias_graph
from .sanitizer import SanitizerCall, find_sanitizer_calls


@dataclass
class OperandInfo:
    """Captures alias information for a single operand."""
    is_write: bool
    alias_set: Set[str] = field(default_factory=set)

    def to_dict(self) -> Dict[str, object]:
        return {
            "is_write": self.is_write,
            "alias_set": list(self.alias_set),
        }


@dataclass
class CheckSubgraph:
    """Dependency subgraph for a sanitizer call."""
    function: str
    callee: str
    operands: List[str]
    details: Dict[str, OperandInfo] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        return {
            "function": self.function,
            "check": self.callee,
            "operands": self.operands,
            "aliases": {op: info.to_dict() for op, info in self.details.items()},
        }


class SubgraphBuilder:
    """Builds dependency subgraphs for sanitizer calls using alias analysis."""

    def __init__(self, module: llvm.ModuleRef) -> None:
        self.module = module
        self.alias_graph: AliasGraph = build_alias_graph(module)
        self.calls: List[SanitizerCall] = find_sanitizer_calls(module)

    def build_for_call(self, call: SanitizerCall) -> CheckSubgraph:
        details: Dict[str, OperandInfo] = {}
        for op in call.operands:
            node = Pointer(name=op, is_write=False)
            alias_nodes = self.alias_graph.get_aliases(node)
            is_write = any(n.is_write for n in alias_nodes)
            alias_names = {n.name for n in alias_nodes}
            details[op] = OperandInfo(is_write=is_write, alias_set=alias_names)
        return CheckSubgraph(
            function=call.function,
            callee=call.callee_name,
            operands=list(call.operands),
            details=details,
        )

    def build_all(self) -> Dict[str, CheckSubgraph]:
        subgraphs: Dict[str, CheckSubgraph] = {}
        for idx, call in enumerate(self.calls):
            # create a unique key based on function and index
            key = f"{call.function}:call{idx}"
            subgraphs[key] = self.build_for_call(call)
        return subgraphs

    def save_json(self, subgraphs: Dict[str, CheckSubgraph], output: str) -> None:
        import json
        serial: Dict[str, object] = {k: sg.to_dict() for k, sg in subgraphs.items()}
        with open(output, "w") as f:
            json.dump(serial, f, indent=2)

    def summary(self, subgraphs: Dict[str, CheckSubgraph]) -> str:
        lines: List[str] = []
        for k, sg in subgraphs.items():
            lines.append(f"{k}: {sg.callee} in {sg.function} with {len(sg.operands)} ops")
        return "\n".join(lines)