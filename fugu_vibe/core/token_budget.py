"""Token budget tracking for Fugu orchestration costs."""

from __future__ import annotations

from dataclasses import dataclass

from fugu_vibe.api.stream_parser import TokenUsage


@dataclass(frozen=True)
class TokenBudgetAlert:
    """A budget warning or critical threshold crossing."""

    level: str
    message: str
    total_tokens: int
    budget_ratio: float
    orchestration_ratio: float
    estimated_cost_usd: float | None = None

    def to_dict(self) -> dict[str, float | int | str | None]:
        return {
            "level": self.level,
            "message": self.message,
            "total_tokens": self.total_tokens,
            "budget_ratio": self.budget_ratio,
            "orchestration_ratio": self.orchestration_ratio,
            "estimated_cost_usd": self.estimated_cost_usd,
        }


@dataclass(frozen=True)
class TokenBudget:
    """Evaluate token usage against total and orchestration budgets."""

    max_total_tokens: int
    max_orchestration_ratio: float = 0.5
    warning_ratio: float = 0.8
    cost_per_million_tokens: float = 0.0

    def check(self, usage: TokenUsage) -> TokenBudgetAlert | None:
        total = usage.total_tokens or (
            usage.input_tokens + usage.output_tokens + usage.orchestration_tokens
        )
        if total <= 0 or self.max_total_tokens <= 0:
            return None

        budget_ratio = total / self.max_total_tokens
        orchestration_ratio = usage.orchestration_tokens / total
        estimated_cost = self._estimate_cost(total)

        if budget_ratio >= 1.0:
            return TokenBudgetAlert(
                level="critical",
                message=f"Token budget exceeded ({budget_ratio:.0%} used)",
                total_tokens=total,
                budget_ratio=budget_ratio,
                orchestration_ratio=orchestration_ratio,
                estimated_cost_usd=estimated_cost,
            )
        if orchestration_ratio > self.max_orchestration_ratio:
            return TokenBudgetAlert(
                level="warning",
                message=(
                    f"Orchestration overhead {orchestration_ratio:.0%}; "
                    "consider simplifying the task or lowering effort"
                ),
                total_tokens=total,
                budget_ratio=budget_ratio,
                orchestration_ratio=orchestration_ratio,
                estimated_cost_usd=estimated_cost,
            )
        if budget_ratio >= self.warning_ratio:
            return TokenBudgetAlert(
                level="warning",
                message=f"Token budget {budget_ratio:.0%} consumed",
                total_tokens=total,
                budget_ratio=budget_ratio,
                orchestration_ratio=orchestration_ratio,
                estimated_cost_usd=estimated_cost,
            )
        return None

    def _estimate_cost(self, total_tokens: int) -> float | None:
        if self.cost_per_million_tokens <= 0:
            return None
        return (total_tokens / 1_000_000) * self.cost_per_million_tokens
