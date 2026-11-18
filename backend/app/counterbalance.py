"""4x4 balanced Latin square (Williams design) for condition order.

Row r gives the order in which participant number r (mod 4) sees the conditions.
Properties (checked in tests/test_counterbalance.py):
  * every condition appears exactly once in every row and every position;
  * every condition immediately precedes every other condition exactly once
    across the four rows (first-order carryover balance).
"""
from __future__ import annotations

CONDITIONS = ["NEUTRAL", "STRICT", "GENERIC_ENCOURAGING", "APPRAISAL_TAILORED"]


def balanced_latin_square(n: int) -> list[list[int]]:
    """Williams design for even n: first row 0, 1, n-1, 2, n-2, ...; later rows add r mod n."""
    if n % 2:
        raise ValueError("A single balanced Latin square needs an even number of conditions")
    first, lo, hi = [0], 1, n - 1
    take_lo = True
    while len(first) < n:
        if take_lo:
            first.append(lo)
            lo += 1
        else:
            first.append(hi)
            hi -= 1
        take_lo = not take_lo
    return [[(c + r) % n for c in first] for r in range(n)]


SQUARE = balanced_latin_square(len(CONDITIONS))  # [[0,1,3,2],[1,2,0,3],[2,3,1,0],[3,0,2,1]]


def latin_row_for(participant_number: int) -> int:
    """Round-robin assignment: participant 1 -> row 0, 2 -> row 1, ..., 5 -> row 0."""
    return (participant_number - 1) % len(SQUARE)


def condition_order(participant_number: int, conditions: list[str] = CONDITIONS) -> tuple[int, list[str]]:
    row = latin_row_for(participant_number)
    return row, [conditions[i] for i in SQUARE[row]]
