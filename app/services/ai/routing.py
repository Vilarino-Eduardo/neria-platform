"""Decisões determinísticas tomadas antes de qualquer chamada ao provedor de IA."""

from dataclasses import dataclass
from enum import StrEnum

from app.services.ai.contracts import RetrievedKnowledge


class AIRoute(StrEnum):
    LOCAL = "local"
    PROVIDER = "provider"
    HANDOFF = "handoff"


@dataclass(frozen=True)
class AIRoutingDecision:
    route: AIRoute
    reason: str

    @property
    def would_use_paid_provider(self) -> bool:
        return self.route == AIRoute.PROVIDER


def decide_ai_route(
    knowledge: list[RetrievedKnowledge], *, quota_available: bool = True
) -> AIRoutingDecision:
    """Espelha o preflight da tarefa real sem reservar cota ou acessar a rede."""
    if knowledge and all(item.chunk_id.startswith("profile:") for item in knowledge):
        return AIRoutingDecision(AIRoute.LOCAL, "structured_company_profile")
    if not knowledge:
        return AIRoutingDecision(AIRoute.HANDOFF, "no_relevant_knowledge")
    if not quota_available:
        return AIRoutingDecision(AIRoute.HANDOFF, "daily_ai_limit_reached")
    return AIRoutingDecision(AIRoute.PROVIDER, "relevant_knowledge_found")
