from app.services.ai.contracts import RetrievedKnowledge
from app.services.ai.routing import AIRoute, decide_ai_route


def knowledge(chunk_id: str) -> RetrievedKnowledge:
    return RetrievedKnowledge(
        chunk_id=chunk_id,
        source_title="Fonte",
        content="Conteúdo",
        score=1.0,
    )


def test_profile_only_is_answered_locally() -> None:
    decision = decide_ai_route([knowledge("profile:opening_hours")])
    assert decision.route == AIRoute.LOCAL
    assert decision.would_use_paid_provider is False


def test_relevant_document_would_use_provider() -> None:
    decision = decide_ai_route([knowledge("knowledge:chunk-1")])
    assert decision.route == AIRoute.PROVIDER
    assert decision.would_use_paid_provider is True


def test_missing_knowledge_or_quota_routes_to_human() -> None:
    assert decide_ai_route([]).reason == "no_relevant_knowledge"
    limited = decide_ai_route(
        [knowledge("knowledge:chunk-1")], quota_available=False
    )
    assert limited.route == AIRoute.HANDOFF
    assert limited.reason == "daily_ai_limit_reached"
