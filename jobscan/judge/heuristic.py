"""Free, offline stand-in for Jev: keyword rules that fill the same schema.
Lets the whole pipeline run end to end today. Also a useful baseline to
measure Jev against later (same jobs, compare buckets)."""
from __future__ import annotations

import re

from jobscan.judge.base import Judge
from jobscan.models import Fit, Flags, Gates, JobVerdict, RawJob, RoleFamily

YES, MAYBE, NO = 0.95, 0.5, 0.05


def _p(text: str, pattern: str, hit: float = YES, miss: float = NO) -> float:
    return hit if re.search(pattern, text, re.I) else miss


ROLE_PATTERNS = [
    (RoleFamily.product, r"product (manager|owner|analyst)|\bapm\b"),
    (RoleFamily.quant_dev, r"quant(itative)? (developer|dev|engineer|research)|trading systems"),
    (RoleFamily.tech_risk, r"technology risk|tech risk|it audit|cyber risk"),
    (RoleFamily.consulting, r"consult"),
    (RoleFamily.data_science, r"data scien|data analy|analytics"),
    (RoleFamily.swe_ai_ml, r"software|developer|engineer|machine learning|\bml\b|\bai\b"),
]


class HeuristicJudge(Judge):
    def judge(self, job: RawJob) -> JobVerdict:
        t = job.as_text()
        title = job.title

        # "3+ years", "at least 4 years", "5-7 years of experience" (first number = minimum)
        exp_years = [int(n) for n in re.findall(
            r"(\d{1,2})\s*\+?\s*(?:-|–|to)?\s*(?:\d{1,2}\s*)?\+?\s*years?", t, re.I)]
        too_senior = any(3 <= n < 20 for n in exp_years)
        junior_years = any(n <= 2 for n in exp_years) and not too_senior
        # Entry-level signal must be explicit. "graduate" alone is too loose
        # ("graduate degree"), so match graduate-scheme phrasing instead.
        entry_title = re.search(r"\b(graduate|grad|new grad|junior|jr\.?|entry[- ]level|early career|"
                                r"trainee|associate|apprentice|campus|university|class of 20\d\d|"
                                r"20(26|27) start)\b", title, re.I)
        entry_text = re.search(r"new grad|graduate (scheme|programme|program|role|position|intake|"
                               r"engineer|developer|opportunit)|recent graduates?|early[- ]careers?|"
                               r"entry[- ]level|junior|no (prior|previous) experience|"
                               r"(final[- ]year|graduating) students?|class of 20(26|27)", t, re.I)
        if too_senior:
            exp = NO
        elif entry_title or entry_text or junior_years:
            exp = YES
        elif job.light_data:
            exp = MAYBE  # alert snippets: the board's own entry-level filter already applied
        else:
            exp = 0.1    # full posting with no entry-level signal = mid-level by default
        grad_words = entry_title or entry_text

        gates = Gates(
            offers_sponsorship=_p(t, r"visa sponsorship (is )?(available|offered|provided)|"
                                     r"(we|will) sponsor|sponsorship available", miss=MAYBE),
            no_sponsorship_wording=_p(t, r"(must|need to) (already )?have (the )?(full )?right to work|"
                                         r"(unable|not able|cannot) to (offer|provide) (visa )?sponsorship|"
                                         r"sponsorship (is )?not available|no sponsorship"),
            accepts_sept_2027_finish=(NO if re.search(r"graduat\w* (by|before) (june|july|august) 2027|"
                                                      r"(june|july|august) 2027 start", t, re.I)
                                      else YES if re.search(r"2027|2028", t) else MAYBE),
            max_2_years_experience=exp,
            requires_clearance=_p(t, r"\b(sc|dv|security) clearance|\bdv\b cleared|eligible for sc|bpss and sc"),
            requires_a_level_maths=_p(t, r"a[- ]level (further )?math"),
            uk_based=YES if job.location else MAYBE,  # prefilter already dropped non-UK
        )

        role = next((r for r, pat in ROLE_PATTERNS if re.search(pat, title, re.I)), RoleFamily.other)
        py = 5 if re.search(r"\bpython\b", t, re.I) else 2
        ml = 5 if re.search(r"machine learning|\bml\b|deep learning|\bllm|pytorch|\bai\b", t, re.I) else 1
        match = 2 + (1 if grad_words else 0) + (1 if py >= 4 else 0) + (1 if ml >= 4 else 0)
        if role == RoleFamily.other:
            match = min(match, 2)

        flags = Flags(
            agency_or_recruiter=_p(t, r"recruitment (agency|consultancy)|on behalf of (our|a) client"),
            one_app_per_cycle=_p(t, r"(only|one) (one )?application per (cycle|season|year)"),
            unpaid_or_commission=_p(t, r"\bunpaid\b|commission only|ote\b"),
        )
        return JobVerdict(gates=gates,
                          fit=Fit(role_family=role, python_centrality=py, ml_relevance=ml,
                                  profile_match=max(1, min(5, match))),
                          flags=flags)
