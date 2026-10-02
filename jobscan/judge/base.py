from __future__ import annotations

from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor

from jobscan.models import JobVerdict, RawJob


class Judge(ABC):
    def __init__(self, profile: str):
        self.profile = profile

    @abstractmethod
    def judge(self, job: RawJob) -> JobVerdict: ...

    def judge_many(self, jobs: list[RawJob], workers: int = 8) -> list[JobVerdict | Exception]:
        """Parallel calls. A failed job returns its exception instead of
        killing the run; route.py sends those to Check manually."""
        def safe(j):
            try:
                return self.judge(j)
            except Exception as e:  # noqa: BLE001
                return e
        with ThreadPoolExecutor(max_workers=workers) as pool:
            return list(pool.map(safe, jobs))
