"""The judge layer. Everything downstream only sees `Judge` and `JobVerdict`,
so swapping heuristic -> Jev is a one-line config change."""
from __future__ import annotations

from jobscan.judge.base import Judge


def make_judge(kind: str, profile: str) -> Judge:
    if kind == "heuristic":
        from jobscan.judge.heuristic import HeuristicJudge
        return HeuristicJudge(profile)
    if kind == "jev":
        from jobscan.judge.jev import JevJudge
        return JevJudge(profile)
    raise ValueError(f"Unknown judge: {kind}")
