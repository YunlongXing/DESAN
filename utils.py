"""
utils.py
--------

Generic utility functions for analysing LLVM IR modules outside of the
core alias and redundancy analyses.  These helpers provide routines
to collect statistics, group instructions by opcode, count occurrences
of certain patterns, and produce simple textual summaries of IR
contents.  None of these functions modify the module; they are
intended for reporting or diagnostics.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Tuple
from llvmlite import binding as llvm


def count_instructions_by_opcode(module: llvm.ModuleRef) -> Dict[str, int]:
    """Return a mapping of opcode names to their counts across the module."""
    counts: Dict[str, int] = {}
    for func in module.functions:
        for block in func.basic_blocks:
            for instr in block.instructions:
                op = instr.opcode
                counts[op] = counts.get(op, 0) + 1
    return counts


def group_instructions_by_opcode(module: llvm.ModuleRef) -> Dict[str, List[llvm.ValueRef]]:
    """Group instructions by opcode in a dictionary."""
    groups: Dict[str, List[llvm.ValueRef]] = {}
    for func in module.functions:
        for block in func.basic_blocks:
            for instr in block.instructions:
                op = instr.opcode
                groups.setdefault(op, []).append(instr)
    return groups


def function_instruction_map(module: llvm.ModuleRef) -> Dict[str, List[llvm.ValueRef]]:
    """Map each function to a list of its instructions."""
    mapping: Dict[str, List[llvm.ValueRef]] = {}
    for func in module.functions:
        instructions: List[llvm.ValueRef] = []
        for block in func.basic_blocks:
            for instr in block.instructions:
                instructions.append(instr)
        mapping[func.name] = instructions
    return mapping


def summarize_ir(module: llvm.ModuleRef) -> str:
    """Generate a summary string with basic IR statistics."""
    counts = count_instructions_by_opcode(module)
    lines: List[str] = []
    total = sum(counts.values())
    lines.append(f"Total instructions: {total}")
    for op, cnt in sorted(counts.items(), key=lambda x: x[0]):
        lines.append(f"  {op}: {cnt}")
    return "\n".join(lines)


def collect_global_variables(module: llvm.ModuleRef) -> List[str]:
    """Return a list of names of global variables in the module."""
    names: List[str] = []
    for gv in module.global_variables:
        names.append(str(gv))
    return names


def count_calls_to_function(module: llvm.ModuleRef, func_name: str) -> int:
    """Count how many times a function is called directly in the module."""
    count = 0
    for func in module.functions:
        for block in func.basic_blocks:
            for instr in block.instructions:
                if instr.opcode == "call" and instr.operands:
                    callee = str(instr.operands[-1])
                    if callee == func_name:
                        count += 1
    return count


def list_functions(module: llvm.ModuleRef) -> List[str]:
    """List all function names in the module."""
    return [func.name for func in module.functions]


def extract_operands(instr: llvm.ValueRef) -> List[str]:
    """Return a list of stringified operands for an instruction."""
    ops: List[str] = []
    for op in instr.operands:
        ops.append(str(op))
    return ops


def is_global_value(name: str) -> bool:
    """Check if a given name refers to a global value."""
    return name.startswith("@")


def find_instructions_with_operand(module: llvm.ModuleRef, operand_name: str) -> List[llvm.ValueRef]:
    """Return all instructions that reference a given operand by name."""
    result: List[llvm.ValueRef] = []
    for func in module.functions:
        for block in func.basic_blocks:
            for instr in block.instructions:
                for op in instr.operands:
                    if str(op) == operand_name:
                        result.append(instr)
                        break
    return result


def count_basic_blocks(module: llvm.ModuleRef) -> int:
    """Count the total number of basic blocks in the module."""
    count = 0
    for func in module.functions:
        count += len(func.basic_blocks)
    return count


def format_function_summary(summary: Dict[str, int]) -> str:
    """Format a dictionary of counts as a multi-line string."""
    lines: List[str] = []
    for name, count in sorted(summary.items(), key=lambda x: x[0]):
        lines.append(f"{name}: {count}")
    return "\n".join(lines)


def search_calls_by_keyword(module: llvm.ModuleRef, keyword: str) -> List[str]:
    """Find callee names of call instructions that contain the given keyword."""
    matches: List[str] = []
    for func in module.functions:
        for block in func.basic_blocks:
            for instr in block.instructions:
                if instr.opcode == "call" and instr.operands:
                    callee = str(instr.operands[-1])
                    if keyword in callee:
                        matches.append(callee)
    return matches


def find_instructions_of_type(module: llvm.ModuleRef, opcode: str) -> List[llvm.ValueRef]:
    """Alias of collect_instructions_of_opcode defined in analysis_utils."""
    from .analysis_utils import collect_instructions_of_opcode
    return collect_instructions_of_opcode(module, opcode)


def generate_report(module: llvm.ModuleRef) -> str:
    """Generate a human-readable summary report of the module's structure."""
    lines: List[str] = []
    lines.append("Module Report")
    lines.append("=============")
    lines.append("")
    # list functions
    funcs = list_functions(module)
    lines.append("Functions:")
    for fn in funcs:
        lines.append(f"  {fn}")
    lines.append("")
    lines.append("Global Variables:")
    for gv in collect_global_variables(module):
        lines.append(f"  {gv}")
    lines.append("")
    lines.append("Instruction Counts:")
    counts = count_instructions_by_opcode(module)
    for op, cnt in sorted(counts.items(), key=lambda x: x[0]):
        lines.append(f"  {op}: {cnt}")
    lines.append("")
    lines.append(f"Basic Blocks: {count_basic_blocks(module)}")
    return "\n".join(lines)