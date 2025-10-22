"""
alias_analysis.py
-----------------

This module implements a basic pointer alias and call graph analysis for
LLVM IR.  The analysis operates on the `llvmlite` representation of an
LLVM module and builds a graph where nodes represent pointer values and
edges capture simple alias relations induced by pointer assignments and
getelementptr instructions.  A companion call graph captures direct
function call relationships, which can be used to propagate alias
information interprocedurally.  The analysis is deliberately simple and
flow-insensitive, trading precision for speed and ease of understanding.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Set, Tuple
from llvmlite import binding as llvm


@dataclass(eq=True, frozen=True)
class Pointer:
    """A node in the alias graph.  Each pointer is identified by a
    string (usually the result of `str(operand)` from llvmlite) and
    optionally annotated as a write site."""
    name: str
    is_write: bool = False


@dataclass
class AliasGraph:
    """Directed graph capturing potential aliasing relationships between pointers."""
    nodes: Set[Pointer] = field(default_factory=set)
    edges: Dict[Pointer, Set[Pointer]] = field(default_factory=dict)

    def add_node(self, node: Pointer) -> None:
        if node not in self.nodes:
            self.nodes.add(node)
            self.edges[node] = set()

    def add_edge(self, src: Pointer, dst: Pointer) -> None:
        self.add_node(src)
        self.add_node(dst)
        self.edges[src].add(dst)

    def get_aliases(self, node: Pointer) -> Set[Pointer]:
        visited: Set[Pointer] = set()
        stack: List[Pointer] = [node]
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            for succ in self.edges.get(current, ()):  # empty tuple when no edges
                stack.append(succ)
        return visited

    def reverse_aliases(self, target: Pointer) -> Set[Pointer]:
        preds: Set[Pointer] = set()
        for src, dests in self.edges.items():
            if target in dests:
                preds.add(src)
        return preds

    def points_to_sets(self) -> Dict[Pointer, Set[Pointer]]:
        pts: Dict[Pointer, Set[Pointer]] = {}
        for node in self.nodes:
            pts[node] = self.get_aliases(node)
        return pts

    def alias_intersection(self, a: Iterable[Pointer], b: Iterable[Pointer]) -> bool:
        set_a = set(a)
        set_b = set(b)
        return not set_a.isdisjoint(set_b)


class CallGraph:
    """Simple directed graph mapping callers to callees and vice versa."""
    def __init__(self) -> None:
        self.calls: Dict[str, Set[str]] = {}
        self.reverse_calls: Dict[str, Set[str]] = {}

    def add_call(self, caller: str, callee: str) -> None:
        if caller not in self.calls:
            self.calls[caller] = set()
        if callee not in self.reverse_calls:
            self.reverse_calls[callee] = set()
        self.calls[caller].add(callee)
        self.reverse_calls[callee].add(caller)

    def get_callees(self, caller: str) -> Set[str]:
        return self.calls.get(caller, set())

    def get_callers(self, callee: str) -> Set[str]:
        return self.reverse_calls.get(callee, set())


def parse_bitcode(bc_path: str) -> llvm.ModuleRef:
    with open(bc_path, "rb") as f:
        data = f.read()
    llvm.initialize()
    llvm.initialize_native_target()
    llvm.initialize_native_asmprinter()
    try:
        return llvm.parse_bitcode(data)
    except Exception:
        asm = data.decode("utf-8")
        mod = llvm.parse_assembly(asm)
        mod.verify()
        return mod


def build_alias_graph(module: llvm.ModuleRef) -> AliasGraph:
    graph = AliasGraph()
    for func in module.functions:
        for block in func.basic_blocks:
            for instr in block.instructions:
                op = instr.opcode
                # store instructions mark writes
                if op == "store":
                    # operands[1] is the destination pointer in llvmlite
                    ptr = instr.operands[1]
                    node = Pointer(name=str(ptr), is_write=True)
                    graph.add_node(node)
                # load and other conversions create alias edges from operand to result
                elif op in ("load", "bitcast", "inttoptr", "ptrtoint"):
                    if len(instr.operands) > 0:
                        src_ptr = instr.operands[0]
                        dst_ptr = instr
                        src_node = Pointer(name=str(src_ptr), is_write=False)
                        dst_node = Pointer(name=str(dst_ptr), is_write=False)
                        graph.add_edge(src_node, dst_node)
                # getelementptr extends alias from base pointer to result
                elif op == "getelementptr":
                    base_ptr = instr.operands[0]
                    res_ptr = instr
                    src_node = Pointer(name=str(base_ptr), is_write=False)
                    dst_node = Pointer(name=str(res_ptr), is_write=False)
                    graph.add_edge(src_node, dst_node)
    return graph


def build_call_graph(module: llvm.ModuleRef) -> CallGraph:
    cg = CallGraph()
    for func in module.functions:
        for block in func.basic_blocks:
            for instr in block.instructions:
                if instr.opcode == "call" and instr.operands:
                    callee = str(instr.operands[-1])
                    if callee.startswith("@"):  # ignore indirect calls via function pointers
                        cg.add_call(func.name, callee)
    return cg


def alias_set_for_value(graph: AliasGraph, value: str) -> Set[str]:
    base = Pointer(name=value, is_write=False)
    aliases = graph.get_aliases(base)
    return {n.name for n in aliases}


def merge_alias_sets(sets: Iterable[Set[str]]) -> Set[str]:
    merged: Set[str] = set()
    for s in sets:
        merged.update(s)
    return merged


def any_write_alias(graph: AliasGraph, operands: Iterable[str]) -> bool:
    for op in operands:
        node = Pointer(name=op, is_write=False)
        # check if this operand or any alias is a write
        for alias in graph.get_aliases(node):
            if alias.is_write:
                return True
    return False


def alias_intersection(graph: AliasGraph, ops_a: Iterable[str], ops_b: Iterable[str]) -> bool:
    for a in ops_a:
        set_a = {n.name for n in graph.get_aliases(Pointer(name=a, is_write=False))}
        for b in ops_b:
            set_b = {n.name for n in graph.get_aliases(Pointer(name=b, is_write=False))}
            if set_a & set_b:
                return True
    return False


def print_graph(graph: AliasGraph) -> None:
    for node in graph.nodes:
        succ = graph.edges.get(node, set())
        succ_names = [n.name for n in succ]
        w = "W" if node.is_write else "R"
        print(f"{node.name} ({w}) -> {succ_names}")