"""
analysis_utils.py
-----------------

Supplementary utilities for performing more sophisticated static
analyses on LLVM IR.  These utilities are provided separately from
`alias_analysis.py` to keep the core alias analysis concise.  While
basic alias and call graphs are sufficient for a simple redundancy
analysis, more advanced analyses can further refine which sanitizer
checks to eliminate.  This module introduces additional data flow
structures and traversal functions that users can leverage in custom
experiments or downstream tools.

The API includes:

* `FunctionSummary`: captures basic statistics about a function
  including its number of calls, stores, loads and whether it
  interacts with global state.
* `collect_function_summaries`: gathers summaries for all functions in
  a module.
* `InstructionVisitor`: a generic visitor pattern implementation for
  traversing instructions in a function with custom callbacks.
* `points_to`: compute a naive points‑to set for pointers using a
  conservative algorithm.
* `may_alias`: checks whether two values may alias based on points‑to
  information.

These utilities are intentionally simple; they do not provide the
precision of production static analysis frameworks.  However, they
illustrate how to structure additional analyses in a way that can
inform more nuanced redundancy heuristics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Set, Tuple
from llvmlite import binding as llvm


@dataclass
class FunctionSummary:
    name: str
    num_instructions: int = 0
    num_calls: int = 0
    num_stores: int = 0
    num_loads: int = 0
    uses_globals: bool = False
    called_functions: Set[str] = field(default_factory=set)

    def update(self, instr: llvm.ValueRef) -> None:
        self.num_instructions += 1
        op = instr.opcode
        if op == "call":
            self.num_calls += 1
            if instr.operands:
                callee = str(instr.operands[-1])
                if callee.startswith("@"):  # direct call
                    self.called_functions.add(callee)
        elif op == "store":
            self.num_stores += 1
            ptr = instr.operands[1]
            if "@" in str(ptr):
                self.uses_globals = True
        elif op == "load":
            self.num_loads += 1
            ptr = instr.operands[0]
            if "@" in str(ptr):
                self.uses_globals = True

    def __str__(self) -> str:
        return (
            f"Function {self.name}: instr={self.num_instructions}, calls={self.num_calls},"
            f" stores={self.num_stores}, loads={self.num_loads}, globals={self.uses_globals}"
        )


def collect_function_summaries(module: llvm.ModuleRef) -> Dict[str, FunctionSummary]:
    """Collect basic statistics about each function in the module."""
    summaries: Dict[str, FunctionSummary] = {}
    for func in module.functions:
        summary = FunctionSummary(name=func.name)
        for block in func.basic_blocks:
            for instr in block.instructions:
                summary.update(instr)
        summaries[func.name] = summary
    return summaries


class InstructionVisitor:
    """Generic visitor for LLVM instructions within a function.

    The visitor allows a user to provide a set of callbacks keyed by
    opcode names.  During traversal of the function's basic blocks
    (depth‑first), the visitor looks up a handler for each instruction's
    opcode and invokes it.  A default handler can be supplied via the
    special key `'*'`.
    """

    def __init__(self, handlers: Dict[str, Callable[[llvm.ValueRef], None]]):
        self.handlers = handlers

    def visit(self, func: llvm.ValueRef) -> None:
        for block in func.basic_blocks:
            for instr in block.instructions:
                op = instr.opcode
                handler = self.handlers.get(op) or self.handlers.get("*")
                if handler:
                    handler(instr)


def points_to(module: llvm.ModuleRef) -> Dict[str, Set[str]]:
    """Compute a naive points‑to relation for each pointer value.

    The algorithm is conservative: when a pointer is assigned to
    another or a getelementptr is taken, we propagate the points‑to
    sets accordingly.  It does not distinguish between different
    memory locations or take control flow into account, but it serves
    as a starting point for alias queries.
    """
    pts: Dict[str, Set[str]] = {}
    # initialize each pointer with an empty set pointing to itself
    def init(name: str) -> None:
        if name not in pts:
            pts[name] = {name}
    for func in module.functions:
        for block in func.basic_blocks:
            for instr in block.instructions:
                if instr.opcode == "alloca":
                    init(str(instr))
                elif instr.opcode == "store":
                    # operand0 is value, operand1 is pointer
                    dest = instr.operands[1]
                    init(str(dest))
                elif instr.opcode == "load":
                    src = instr.operands[0]
                    init(str(src))
                elif instr.opcode == "bitcast":
                    src = instr.operands[0]
                    dst = str(instr)
                    init(dst)
                    init(str(src))
                    pts[dst].update(pts.get(str(src), {str(src)}))
                elif instr.opcode == "getelementptr":
                    base = instr.operands[0]
                    dst = str(instr)
                    init(dst)
                    init(str(base))
                    pts[dst].update(pts.get(str(base), {str(base)}))
    return pts


def may_alias(a: str, b: str, pts: Dict[str, Set[str]]) -> bool:
    """Determine if two pointer values may alias using points‑to sets."""
    set_a = pts.get(a)
    set_b = pts.get(b)
    if set_a is None or set_b is None:
        return False
    return not set_a.isdisjoint(set_b)


def find_aliasing_pairs(values: Iterable[str], pts: Dict[str, Set[str]]) -> List[Tuple[str, str]]:
    """Return all unordered pairs of values that may alias."""
    vals = list(values)
    pairs: List[Tuple[str, str]] = []
    for i in range(len(vals)):
        for j in range(i + 1, len(vals)):
            if may_alias(vals[i], vals[j], pts):
                pairs.append((vals[i], vals[j]))
    return pairs


def collect_store_sites(module: llvm.ModuleRef) -> Set[str]:
    """Collect all values that participate as destinations in store instructions."""
    sites: Set[str] = set()
    for func in module.functions:
        for block in func.basic_blocks:
            for instr in block.instructions:
                if instr.opcode == "store":
                    dest = instr.operands[1]
                    sites.add(str(dest))
    return sites


def function_uses_value(func: llvm.ValueRef, value_name: str) -> bool:
    """Check whether a function uses a value anywhere in its body."""
    for block in func.basic_blocks:
        for instr in block.instructions:
            for operand in instr.operands:
                if str(operand) == value_name:
                    return True
    return False


def build_reverse_call_graph(module: llvm.ModuleRef) -> Dict[str, Set[str]]:
    """Build a mapping from callee names to the set of callers."""
    rc: Dict[str, Set[str]] = {}
    for func in module.functions:
        for block in func.basic_blocks:
            for instr in block.instructions:
                if instr.opcode == "call" and instr.operands:
                    callee = str(instr.operands[-1])
                    if callee.startswith("@"):  # direct call
                        rc.setdefault(callee, set()).add(func.name)
    return rc


def propagate_globals(module: llvm.ModuleRef) -> Dict[str, bool]:
    """Propagate global usage information through the call graph.

    For each function, record whether it or any of its callees touch
    global memory.  Use a simple fixed point iteration.
    """
    summaries = collect_function_summaries(module)
    rc = build_reverse_call_graph(module)
    # initialize global usage map
    uses: Dict[str, bool] = {name: summary.uses_globals for name, summary in summaries.items()}
    changed = True
    while changed:
        changed = False
        for callee, callers in rc.items():
            if uses.get(callee):
                for caller in callers:
                    if not uses.get(caller, False):
                        uses[caller] = True
                        changed = True
    return uses


def estimate_check_cost(call: llvm.ValueRef) -> int:
    """Estimate a cost for a sanitizer call.  This simple heuristic returns
    a constant cost based on sanitizer type, which could be used for
    ranking checks.  The cost values here are arbitrary placeholders.
    """
    name = ""
    if call.operands:
        name = str(call.operands[-1])
    if "__msan" in name:
        return 3  # memory sanitizer is considered heavier
    if "__asan" in name:
        return 2
    if "__ubsan" in name:
        return 1
    if "__tsan" in name or "__lsan" in name:
        return 2
    return 1


def rank_calls_by_cost(calls: Iterable[llvm.ValueRef]) -> List[Tuple[llvm.ValueRef, int]]:
    """Rank sanitizer calls by their estimated cost in descending order."""
    scored: List[Tuple[llvm.ValueRef, int]] = []
    for call in calls:
        cost = estimate_check_cost(call)
        scored.append((call, cost))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


def gather_all_values(module: llvm.ModuleRef) -> Set[str]:
    """Return the set of string representations of all values defined in the module."""
    values: Set[str] = set()
    for func in module.functions:
        for block in func.basic_blocks:
            for instr in block.instructions:
                values.add(str(instr))
                for op in instr.operands:
                    values.add(str(op))
    for gv in module.global_variables:
        values.add(str(gv))
    return values


def collect_instructions_of_opcode(module: llvm.ModuleRef, opcode: str) -> List[llvm.ValueRef]:
    """Collect all instructions with a given opcode across the module."""
    insts: List[llvm.ValueRef] = []
    for func in module.functions:
        for block in func.basic_blocks:
            for instr in block.instructions:
                if instr.opcode == opcode:
                    insts.append(instr)
    return insts


def filter_calls_by_sanitizer(calls: Iterable[llvm.ValueRef], keyword: str) -> List[llvm.ValueRef]:
    """Return only those call instructions whose callee names contain the given keyword."""
    out: List[llvm.ValueRef] = []
    for call in calls:
        if call.operands and keyword in str(call.operands[-1]):
            out.append(call)
    return out