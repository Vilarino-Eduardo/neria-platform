import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from app.api.dependencies import CurrentUser, DatabaseSession
from app.core.settings import get_settings
from app.models.core import (
    AIConfiguration,
    AIFeedback,
    AIFeedbackRating,
    AIRun,
    AIRunStatus,
    AIUsageDaily,
    KnowledgeSourceType,
    KnowledgeSuggestion,
    KnowledgeSuggestionStatus,
    Message,
    OrganizationProfile,
    Subscription,
    UserRole,
)
from app.schemas.ai import (
    AIConfigurationResponse,
    AIConfigurationUpdate,
    AIFeedbackCreate,
    AIFeedbackResponse,
    AIMetricsResponse,
    AIRunSummaryResponse,
    AISimulationRequest,
    AISimulationResponse,
    AISimulationSource,
    KnowledgeSuggestionResponse,
)
from app.services.ai.context import retrieve_profile_knowledge
from app.services.ai.retrieval import LexicalKnowledgeRetriever
from app.services.ai.routing import AIRoute, decide_ai_route
from app.services.ai.usage import ai_quota_status
from app.services.knowledge_service import create_processed_source

router = APIRouter(prefix="/ai", tags=["ai"])


def require_admin(current_user: CurrentUser) -> None:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Apenas administradores podem configurar a IA.")


def get_or_create_configuration(
    session: DatabaseSession, organization_id: uuid.UUID
) -> AIConfiguration:
    configuration = session.scalar(
        select(AIConfiguration).where(AIConfiguration.organization_id == organization_id)
    )
    if configuration is None:
        configuration = AIConfiguration(organization_id=organization_id)
        session.add(configuration)
        session.commit()
        session.refresh(configuration)
    return configuration


@router.get("/configuration", response_model=AIConfigurationResponse)
def get_ai_configuration(
    session: DatabaseSession, current_user: CurrentUser
) -> AIConfiguration:
    require_admin(current_user)
    return get_or_create_configuration(session, current_user.organization_id)


@router.patch("/configuration", response_model=AIConfigurationResponse)
def update_ai_configuration(
    payload: AIConfigurationUpdate,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> AIConfiguration:
    require_admin(current_user)
    if payload.is_enabled is True and not get_settings().openai_api_key:
        raise HTTPException(
            status_code=409,
            detail="Configure OPENAI_API_KEY antes de ativar a IA.",
        )
    configuration = get_or_create_configuration(session, current_user.organization_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(configuration, field, value)
    session.commit()
    session.refresh(configuration)
    return configuration


@router.post("/simulate", response_model=AISimulationResponse)
def simulate_ai_response(
    payload: AISimulationRequest,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> AISimulationResponse:
    """Exercise knowledge retrieval without calling a paid AI provider."""
    require_admin(current_user)
    configuration = get_or_create_configuration(session, current_user.organization_id)
    knowledge = LexicalKnowledgeRetriever(session).search(
        str(current_user.organization_id), payload.question, configuration.retrieval_limit
    )
    profile = session.scalar(
        select(OrganizationProfile).where(
            OrganizationProfile.organization_id == current_user.organization_id
        )
    )
    knowledge = sorted(
        [*knowledge, *retrieve_profile_knowledge(profile, payload.question)],
        key=lambda item: item.score,
        reverse=True,
    )[: configuration.retrieval_limit]
    subscription = session.scalar(
        select(Subscription).where(
            Subscription.organization_id == current_user.organization_id
        )
    )
    usage = session.get(
        AIUsageDaily, (current_user.organization_id, datetime.now(UTC).date())
    )
    daily_limit = subscription.ai_daily_request_limit if subscription else 0
    daily_token_limit = subscription.ai_daily_token_limit if subscription else 0
    used = usage.request_count if usage else 0
    used_tokens = (
        usage.input_tokens + usage.output_tokens + usage.reserved_tokens if usage else 0
    )
    decision = decide_ai_route(
        knowledge,
        quota_available=used < daily_limit and used_tokens < daily_token_limit,
    )
    confidence = min(95, round(55 + knowledge[0].score * 8)) if knowledge else 0
    if decision.route == AIRoute.LOCAL:
        confidence = 100
        answer = "\n".join(item.content for item in knowledge)
    elif decision.route == AIRoute.PROVIDER:
        answer = (
            "A base contém informação relevante. Na operação real, a pergunta seria "
            "enviada ao modelo de IA para redigir a resposta."
        )
    else:
        confidence = 0
        answer = configuration.fallback_message
    return AISimulationResponse(
        answer=answer,
        confidence=confidence,
        should_handoff=decision.route == AIRoute.HANDOFF,
        route=decision.route,
        reason=decision.reason,
        would_use_paid_provider=decision.would_use_paid_provider,
        external_request_made=False,
        sources=[
            AISimulationSource(
                title=item.source_title,
                content=item.content,
                score=round(item.score, 2),
            )
            for item in knowledge
        ],
    )


@router.get("/metrics", response_model=AIMetricsResponse)
def get_ai_metrics(
    session: DatabaseSession, current_user: CurrentUser
) -> AIMetricsResponse:
    require_admin(current_user)
    since = datetime.now(UTC) - timedelta(days=30)
    run_counts = dict(
        session.execute(
            select(AIRun.status, func.count(AIRun.id))
            .where(
                AIRun.organization_id == current_user.organization_id,
                AIRun.created_at >= since,
            )
            .group_by(AIRun.status)
        ).all()
    )
    feedback_counts = dict(
        session.execute(
            select(AIFeedback.rating, func.count(AIFeedback.id))
            .where(
                AIFeedback.organization_id == current_user.organization_id,
                AIFeedback.created_at >= since,
            )
            .group_by(AIFeedback.rating)
        ).all()
    )
    total = sum(run_counts.values())
    escalated = run_counts.get(AIRunStatus.ESCALATED, 0)
    average_confidence = session.scalar(
        select(func.avg(AIRun.confidence)).where(
            AIRun.organization_id == current_user.organization_id,
            AIRun.created_at >= since,
            AIRun.confidence.is_not(None),
        )
    )
    subscription = session.scalar(
        select(Subscription).where(
            Subscription.organization_id == current_user.organization_id
        )
    )
    daily_limit = subscription.ai_daily_request_limit if subscription else 0
    daily_token_limit = subscription.ai_daily_token_limit if subscription else 0
    daily_usage = session.get(
        AIUsageDaily, (current_user.organization_id, datetime.now(UTC).date())
    )
    paid_requests_today = daily_usage.request_count if daily_usage else 0
    daily_input_tokens = daily_usage.input_tokens if daily_usage else 0
    daily_output_tokens = daily_usage.output_tokens if daily_usage else 0
    daily_reserved_tokens = daily_usage.reserved_tokens if daily_usage else 0
    daily_quota_percent, daily_quota_status = ai_quota_status(
        paid_requests_today, daily_limit
    )
    daily_committed_tokens = (
        daily_input_tokens + daily_output_tokens + daily_reserved_tokens
    )
    daily_token_quota_percent, daily_token_quota_status = ai_quota_status(
        daily_committed_tokens, daily_token_limit
    )
    today = datetime.now(UTC).date()
    usage_start = today - timedelta(days=29)
    usage_rows = {
        item.usage_date: item
        for item in session.scalars(
            select(AIUsageDaily)
            .where(
                AIUsageDaily.organization_id == current_user.organization_id,
                AIUsageDaily.usage_date >= usage_start,
            )
            .order_by(AIUsageDaily.usage_date)
        )
    }
    usage_history = []
    for day_offset in range(30):
        usage_date = usage_start + timedelta(days=day_offset)
        usage = usage_rows.get(usage_date)
        input_tokens = usage.input_tokens if usage else 0
        output_tokens = usage.output_tokens if usage else 0
        usage_history.append(
            {
                "date": usage_date,
                "paid_requests": usage.request_count if usage else 0,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
            }
        )
    version_run_rows = session.execute(
        select(
            AIRun.prompt_version,
            AIRun.status,
            func.count(AIRun.id),
            func.avg(AIRun.confidence),
            func.count(AIRun.confidence),
        )
        .where(
            AIRun.organization_id == current_user.organization_id,
            AIRun.created_at >= since,
        )
        .group_by(AIRun.prompt_version, AIRun.status)
    ).all()
    version_feedback_rows = session.execute(
        select(
            AIRun.prompt_version,
            AIFeedback.rating,
            func.count(AIFeedback.id),
        )
        .join(AIRun, AIRun.id == AIFeedback.ai_run_id)
        .where(
            AIFeedback.organization_id == current_user.organization_id,
            AIFeedback.created_at >= since,
        )
        .group_by(AIRun.prompt_version, AIFeedback.rating)
    ).all()
    versions: dict[str, dict] = {}
    for prompt_version, status, count, confidence, confidence_count in version_run_rows:
        metrics = versions.setdefault(
            prompt_version,
            {
                "prompt_version": prompt_version,
                "total_runs": 0,
                "completed_runs": 0,
                "escalated_runs": 0,
                "failed_runs": 0,
                "confidence_total": 0.0,
                "confidence_count": 0,
                "helpful_feedback": 0,
                "correction_feedback": 0,
            },
        )
        metrics["total_runs"] += count
        metrics[f"{status.value}_runs"] = count
        if confidence is not None:
            metrics["confidence_total"] += float(confidence) * confidence_count
            metrics["confidence_count"] += confidence_count
    for prompt_version, rating, count in version_feedback_rows:
        metrics = versions.get(prompt_version)
        if metrics is not None:
            key = (
                "helpful_feedback"
                if rating == AIFeedbackRating.HELPFUL
                else "correction_feedback"
            )
            metrics[key] = count
    prompt_versions = []
    for metrics in versions.values():
        confidence_count = metrics.pop("confidence_count")
        confidence_total = metrics.pop("confidence_total")
        metrics["average_confidence"] = (
            round(confidence_total / confidence_count) if confidence_count else None
        )
        prompt_versions.append(metrics)
    prompt_versions.sort(
        key=lambda item: (item["total_runs"], item["prompt_version"]), reverse=True
    )
    return AIMetricsResponse(
        period_days=30,
        total_runs=total,
        completed_runs=run_counts.get(AIRunStatus.COMPLETED, 0),
        escalated_runs=escalated,
        failed_runs=run_counts.get(AIRunStatus.FAILED, 0),
        average_confidence=round(float(average_confidence)) if average_confidence else None,
        handoff_rate=round((escalated / total * 100) if total else 0, 1),
        helpful_feedback=feedback_counts.get(AIFeedbackRating.HELPFUL, 0),
        correction_feedback=feedback_counts.get(AIFeedbackRating.UNHELPFUL, 0),
        paid_requests_today=paid_requests_today,
        daily_request_limit=daily_limit,
        daily_requests_remaining=max(0, daily_limit - paid_requests_today),
        daily_quota_percent=daily_quota_percent,
        daily_quota_status=daily_quota_status,
        daily_input_tokens=daily_input_tokens,
        daily_output_tokens=daily_output_tokens,
        daily_total_tokens=daily_input_tokens + daily_output_tokens,
        daily_reserved_tokens=daily_reserved_tokens,
        daily_token_limit=daily_token_limit,
        daily_tokens_remaining=max(0, daily_token_limit - daily_committed_tokens),
        daily_token_quota_percent=daily_token_quota_percent,
        daily_token_quota_status=daily_token_quota_status,
        daily_usage=usage_history,
        prompt_versions=prompt_versions,
    )


@router.get("/runs", response_model=list[AIRunSummaryResponse])
def list_ai_runs(
    session: DatabaseSession,
    current_user: CurrentUser,
    run_status: Annotated[AIRunStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> list[dict]:
    require_admin(current_user)
    statement = select(AIRun).where(
        AIRun.organization_id == current_user.organization_id
    )
    if run_status is not None:
        statement = statement.where(AIRun.status == run_status)
    runs = session.scalars(statement.order_by(AIRun.created_at.desc()).limit(limit))
    return [
        {
            "id": run.id,
            "status": run.status,
            "provider": run.provider,
            "model": run.model,
            "prompt_version": run.prompt_version,
            "source_count": len(run.retrieved_chunk_ids),
            "confidence": run.confidence,
            "latency_ms": run.latency_ms,
            "input_tokens": run.input_tokens,
            "output_tokens": run.output_tokens,
            "error": run.error,
            "created_at": run.created_at,
        }
        for run in runs
    ]


@router.post("/runs/{run_id}/feedback", response_model=AIFeedbackResponse)
def create_ai_feedback(
    run_id: uuid.UUID,
    payload: AIFeedbackCreate,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> AIFeedback:
    run = session.scalar(
        select(AIRun).where(
            AIRun.id == run_id,
            AIRun.organization_id == current_user.organization_id,
        )
    )
    if run is None:
        raise HTTPException(status_code=404, detail="Execução da IA não encontrada.")
    feedback = session.scalar(
        select(AIFeedback).where(
            AIFeedback.ai_run_id == run.id,
            AIFeedback.user_id == current_user.id,
        )
    )
    if feedback is None:
        feedback = AIFeedback(
            organization_id=current_user.organization_id,
            ai_run_id=run.id,
            user_id=current_user.id,
            rating=payload.rating,
            correction=payload.correction,
        )
        session.add(feedback)
    else:
        feedback.rating = payload.rating
        feedback.correction = payload.correction

    if payload.rating == AIFeedbackRating.UNHELPFUL and payload.correction:
        question = session.get(Message, run.input_message_id)
        existing = session.scalar(
            select(KnowledgeSuggestion).where(KnowledgeSuggestion.ai_run_id == run.id)
        )
        if existing is None:
            session.add(
                KnowledgeSuggestion(
                    organization_id=current_user.organization_id,
                    ai_run_id=run.id,
                    question=question.body if question and question.body else "Pergunta sem texto",
                    suggested_content=payload.correction,
                    status=KnowledgeSuggestionStatus.PENDING,
                )
            )
    session.commit()
    session.refresh(feedback)
    return feedback


@router.get("/knowledge-suggestions", response_model=list[KnowledgeSuggestionResponse])
def list_knowledge_suggestions(
    session: DatabaseSession, current_user: CurrentUser
) -> list[KnowledgeSuggestion]:
    require_admin(current_user)
    return list(
        session.scalars(
            select(KnowledgeSuggestion)
            .where(KnowledgeSuggestion.organization_id == current_user.organization_id)
            .order_by(KnowledgeSuggestion.created_at.desc())
        )
    )


@router.post(
    "/knowledge-suggestions/{suggestion_id}/approve",
    response_model=KnowledgeSuggestionResponse,
)
def approve_knowledge_suggestion(
    suggestion_id: uuid.UUID,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> KnowledgeSuggestion:
    require_admin(current_user)
    suggestion = session.scalar(
        select(KnowledgeSuggestion).where(
            KnowledgeSuggestion.id == suggestion_id,
            KnowledgeSuggestion.organization_id == current_user.organization_id,
            KnowledgeSuggestion.status == KnowledgeSuggestionStatus.PENDING,
        )
    )
    if suggestion is None:
        raise HTTPException(status_code=404, detail="Sugestão pendente não encontrada.")
    create_processed_source(
        session,
        organization_id=current_user.organization_id,
        title=f"Resposta aprendida: {suggestion.question[:120]}",
        source_type=KnowledgeSourceType.MANUAL,
        text=f"Pergunta: {suggestion.question}\nResposta: {suggestion.suggested_content}",
    )
    suggestion.status = KnowledgeSuggestionStatus.APPROVED
    suggestion.reviewed_by_user_id = current_user.id
    session.commit()
    session.refresh(suggestion)
    return suggestion


@router.post(
    "/knowledge-suggestions/{suggestion_id}/reject",
    response_model=KnowledgeSuggestionResponse,
)
def reject_knowledge_suggestion(
    suggestion_id: uuid.UUID,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> KnowledgeSuggestion:
    require_admin(current_user)
    suggestion = session.scalar(
        select(KnowledgeSuggestion).where(
            KnowledgeSuggestion.id == suggestion_id,
            KnowledgeSuggestion.organization_id == current_user.organization_id,
            KnowledgeSuggestion.status == KnowledgeSuggestionStatus.PENDING,
        )
    )
    if suggestion is None:
        raise HTTPException(status_code=404, detail="Sugestão pendente não encontrada.")
    suggestion.status = KnowledgeSuggestionStatus.REJECTED
    suggestion.reviewed_by_user_id = current_user.id
    session.commit()
    session.refresh(suggestion)
    return suggestion
