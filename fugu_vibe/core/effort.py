"""Adaptive Fugu reasoning effort selection."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

Effort = Literal["high", "xhigh", "max"]

_PATH_PATTERN = re.compile(r"(?:^|\s)([\w./-]+\.[A-Za-z0-9]{1,8})(?:\s|$)")
_COMPLEX_KEYWORDS = {
    "architecture",
    "checkpoint",
    "cross-module",
    "database",
    "migration",
    "orchestration",
    "refactor",
    "rollback",
    "security",
    "tests",
    "并发",
    "安全",
    "架构",
    "测试",
    "重构",
}


@dataclass(frozen=True)
class EffortDecision:
    """Reasoning effort decision with explainable signals."""

    effort: Effort
    reason: str
    score: int
    signals: list[str] = field(default_factory=list)


def select_effort(
    prompt: str,
    configured_effort: Effort,
    *,
    adaptive: bool = True,
    attachment_count: int = 0,
) -> EffortDecision:
    """Choose high or xhigh based on task complexity unless adaptation is disabled."""
    if not adaptive:
        return EffortDecision(effort=configured_effort, reason="configured effort", score=0)

    score, signals = _complexity_score(prompt, attachment_count=attachment_count)
    if configured_effort == "max":
        return EffortDecision(
            effort="xhigh",
            reason="max effort requested",
            score=score,
            signals=signals,
        )
    if score >= 4:
        return EffortDecision(
            effort="xhigh",
            reason="complex task signals detected",
            score=score,
            signals=signals,
        )
    return EffortDecision(
        effort="high",
        reason="simple task; use lower latency effort",
        score=score,
        signals=signals,
    )


def _complexity_score(prompt: str, *, attachment_count: int = 0) -> tuple[int, list[str]]:
    lowered = prompt.lower()
    signals: list[str] = []
    score = 0

    if len(prompt) > 800:
        score += 2
        signals.append("long_prompt")
    elif len(prompt) > 300:
        score += 1
        signals.append("medium_prompt")

    paths = {match.group(1) for match in _PATH_PATTERN.finditer(prompt)}
    if len(paths) >= 3:
        score += 2
        signals.append("multiple_files")
    elif paths:
        score += 1
        signals.append("file_reference")

    matched_keywords = sorted(keyword for keyword in _COMPLEX_KEYWORDS if keyword in lowered)
    if matched_keywords:
        score += min(len(matched_keywords), 3)
        signals.extend(f"keyword:{keyword}" for keyword in matched_keywords[:3])

    if attachment_count:
        score += min(attachment_count, 2)
        signals.append("attachments")

    return score, signals
