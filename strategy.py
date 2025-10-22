"""
strategy.py
-----------

This module introduces heuristics for ranking sanitizer checks and selecting
which ones to remove first during redundancy elimination.  While the core
redundancy analysis in `redundancy.py` simply removes later checks when
they operate on aliasing values, a more refined strategy might prioritise
elimination of high‑cost checks or those that contribute little to
coverage.  The structures and functions below facilitate such
experiments.

The primary abstraction is a `CheckNode`, which wraps a dependency
subgraph with additional metrics (such as cost, distance from entry,
number of alias overlaps, etc.).  The module then defines functions to
compute ranking scores and to generate an ordered list of redundant
candidates.  These facilities are not used by default but are
available for users wanting to customise the redundancy removal process.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .dependency import CheckSubgraph
from .analysis_utils import estimate_check_cost


@dataclass
class CheckNode:
    key: str
    subgraph: CheckSubgraph
    cost: int = 0
    overlap_count: int = 0
    distance: Optional[int] = None  # optional measure: block or instruction distance

    def compute_score(self) -> float:
        """Compute a composite score for ranking.

        A higher score indicates a better candidate for removal.  The
        formula is arbitrary and can be tuned.  By default we weight
        cost and overlap_count equally and penalise distance.
        """
        score = 0.0
        score += float(self.cost)
        score += float(self.overlap_count)
        if self.distance is not None:
            # shorter distance yields higher score
            score += 1.0 / (1.0 + self.distance)
        return score


def wrap_subgraphs(subgraphs: Dict[str, CheckSubgraph]) -> Dict[str, CheckNode]:
    nodes: Dict[str, CheckNode] = {}
    for key, sg in subgraphs.items():
        # estimate cost using the first operand's callee as heuristics
        cost = 0
        # compute cost: use estimated cost of call based on sanitizer type
        # this uses the analysis_utils estimate_check_cost by faking a call value
        # We cannot pass the actual call instruction here, but we approximate based on name
        if "__msan" in sg.callee:
            cost = 3
        elif "__asan" in sg.callee:
            cost = 2
        elif "__ubsan" in sg.callee:
            cost = 1
        elif "__tsan" in sg.callee or "__lsan" in sg.callee:
            cost = 2
        nodes[key] = CheckNode(key=key, subgraph=sg, cost=cost)
    return nodes


def compute_overlap_counts(nodes: Dict[str, CheckNode]) -> None:
    keys = list(nodes.keys())
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            a = nodes[keys[i]]
            b = nodes[keys[j]]
            # compute alias overlap count between these two subgraphs
            overlaps = 0
            for op_a, info_a in a.subgraph.details.items():
                for op_b, info_b in b.subgraph.details.items():
                    if info_a.alias_set & info_b.alias_set:
                        overlaps += 1
            if overlaps > 0:
                a.overlap_count += overlaps
                b.overlap_count += overlaps


def rank_nodes(nodes: Dict[str, CheckNode]) -> List[Tuple[str, float]]:
    """Return a sorted list of (key, score) pairs from highest to lowest score."""
    # compute overlap counts first
    compute_overlap_counts(nodes)
    scores: List[Tuple[str, float]] = []
    for key, node in nodes.items():
        scores.append((key, node.compute_score()))
    scores.sort(key=lambda x: x[1], reverse=True)
    return scores


def select_redundant_keys(nodes: Dict[str, CheckNode]) -> List[str]:
    """Select redundant keys based on ranking.  This function returns
    a list of keys sorted by decreasing redundancy suitability.  Keys
    that correspond to write operations are excluded.
    """
    candidates: List[str] = []
    for key, node in nodes.items():
        # skip if any operand has a write
        if any(info.is_write for info in node.subgraph.details.values()):
            continue
        candidates.append(key)
    ranked = rank_nodes({k: nodes[k] for k in candidates})
    return [k for k, _ in ranked]