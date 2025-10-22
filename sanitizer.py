"""
sanitizer.py
-------------

Utilities for identifying sanitizer calls within an LLVM module.  A
sanitizer call is defined as any call instruction whose callee name
matches known sanitizer runtime functions.  This module defines a
`SanitizerCall` data class to store information about each call and
provides functions to scan a module for such calls.  The detection
logic can be extended by adding new prefixes or patterns to the
`SANITIZER_PREFIXES` list.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Tuple
from llvmlite import binding as llvm

# recognized sanitizer runtime name fragments
SANITIZER_PREFIXES = [
    "__asan",  # AddressSanitizer
    "__ubsan",  # UndefinedBehaviorSanitizer
    "__msan",  # MemorySanitizer
    "__tsan",  # ThreadSanitizer
    "__lsan",  # LeakSanitizer
]


def is_sanitizer_function(func_name: str) -> bool:
    for prefix in SANITIZER_PREFIXES:
        if prefix in func_name:
            return True
    return False


@dataclass
class SanitizerCall:
    """Represents a call to a sanitizer runtime function in the IR."""
    function: str  # name of the function containing the call
    instruction: llvm.ValueRef  # the call instruction
    callee_name: str  # name of the called sanitizer function
    operands: Tuple[str, ...]  # names of operand values (arguments)

    def __str__(self) -> str:
        ops = ", ".join(self.operands)
        return f"{self.function}:{self.instruction.name} -> {self.callee_name}({ops})"


def find_sanitizer_calls(module: llvm.ModuleRef) -> List[SanitizerCall]:
    """Scan the IR module and collect all sanitizer calls."""
    calls: List[SanitizerCall] = []
    for func in module.functions:
        for block in func.basic_blocks:
            for instr in block.instructions:
                if instr.opcode == "call" and instr.operands:
                    callee = str(instr.operands[-1])
                    if is_sanitizer_function(callee):
                        args: List[str] = []
                        # operands except last are arguments to the call
                        for op in instr.operands[:-1]:
                            args.append(str(op))
                        call = SanitizerCall(
                            function=func.name,
                            instruction=instr,
                            callee_name=callee,
                            operands=tuple(args),
                        )
                        calls.append(call)
    return calls


def list_sanitizer_names() -> List[str]:
    return SANITIZER_PREFIXES.copy()


def call_summary(calls: Iterable[SanitizerCall]) -> str:
    lines: List[str] = []
    for call in calls:
        lines.append(str(call))
    return "\n".join(lines)