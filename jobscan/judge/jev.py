"""TypeSafe AI Jev adapter.

Jev takes text plus a set of typed questions (Boolean / Score / Choice) and
returns calibrated probabilities. This adapter builds those questions straight
from the Field descriptions in models.py, so the schema is defined once.

What is done: question building, response -> JobVerdict mapping.
What is left: `_call()`. Jev is waitlist-only and its request format is not
public yet, so the HTTP shape is not guessed here. When you get access, fill
in `_call()` from the docs (or route through LiteLLM / OpenRouter / Vercel AI
Gateway, which all list Jev). Env: JEV_API_KEY.
"""
from __future__ import annotations

import os
import typing
from enum import Enum

from jobscan.judge.base import Judge
from jobscan.models import Fit, Flags, Gates, JobVerdict, RawJob


def _questions(model: type, prefix: str) -> list[dict]:
    """Turn a pydantic model into Jev question specs."""
    qs = []
    for name, field in model.model_fields.items():
        ann = field.annotation
        spec = {"id": f"{prefix}.{name}", "question": field.description}
        if ann is float:
            spec["type"] = "boolean"            # returns P(yes)
        elif ann is int:
            lo = next(m.ge for m in field.metadata if hasattr(m, "ge"))
            hi = next(m.le for m in field.metadata if hasattr(m, "le"))
            spec.update(type="score", min=lo, max=hi)
        elif isinstance(ann, type) and issubclass(ann, Enum):
            spec.update(type="choice", options=[m.value for m in ann])
        else:
            raise TypeError(f"Unsupported field type for {name}: {ann}")
        qs.append(spec)
    return qs


QUESTIONS = _questions(Gates, "gates") + _questions(Fit, "fit") + _questions(Flags, "flags")


class JevJudge(Judge):
    def __init__(self, profile: str):
        super().__init__(profile)
        self.api_key = os.environ.get("JEV_API_KEY")
        if not self.api_key:
            raise RuntimeError("JEV_API_KEY not set. Use judge: heuristic in settings.yaml until you have access.")

    def build_input(self, job: RawJob) -> str:
        return f"CANDIDATE PROFILE:\n{self.profile}\n\nJOB POSTING:\n{job.as_text()}"

    def _call(self, text: str, questions: list[dict]) -> dict[str, typing.Any]:
        """Send one job + all questions to Jev in a single parallel pass.
        Must return {question_id: answer}, where answer is:
          boolean -> float P(yes)
          score   -> int (the most likely score)
          choice  -> str (the most likely option)
        """
        raise NotImplementedError("Fill in from Jev docs once you have API access.")

    def judge(self, job: RawJob) -> JobVerdict:
        ans = self._call(self.build_input(job), QUESTIONS)

        def section(prefix: str) -> dict:
            return {k.split(".", 1)[1]: v for k, v in ans.items() if k.startswith(prefix + ".")}

        return JobVerdict(gates=Gates(**section("gates")),
                          fit=Fit(**section("fit")),
                          flags=Flags(**section("flags")))
