import time
import uuid

from sqlalchemy import select

from app.core.settings import get_settings
from app.database.session import SessionLocal
from app.models.core import (
    AIConfiguration,
    AIRun,
    AIRunStatus,
    Conversation,
    ConversationMode,
    Message,
    MessageDirection,
    MessageStatus,
    MessageType,
    Subscription,
)
from app.services.ai.context import PROMPT_VERSION, build_ai_request
from app.services.ai.errors import safe_ai_error_code
from app.services.ai.openai_provider import (
    DEFAULT_MAX_OUTPUT_TOKENS,
    OpenAIResponsesProvider,
)
from app.services.ai.retrieval import LexicalKnowledgeRetriever
from app.services.ai.routing import AIRoute, decide_ai_route
from app.services.ai.usage import (
    estimate_token_reservation,
    record_paid_ai_tokens,
    release_ai_token_reservation,
    reserve_paid_ai_request,
)
from app.services.conversation_assignment import assign_conversation_if_needed
from app.tasks.celery_app import celery_app
from app.tasks.whatsapp import enqueue_outbound_message


@celery_app.task(bind=True, name="ai.generate_reply", max_retries=0)
def generate_ai_reply(self, input_message_id: str) -> None:
    message_uuid = uuid.UUID(input_message_id)
    with SessionLocal() as session:
        input_message = session.get(Message, message_uuid)
        if input_message is None or input_message.direction != MessageDirection.INBOUND:
            return
        conversation = session.get(Conversation, input_message.conversation_id)
        configuration = session.scalar(
            select(AIConfiguration).where(
                AIConfiguration.organization_id == input_message.organization_id
            )
        )
        settings = get_settings()
        if (
            conversation is None
            or conversation.mode != ConversationMode.BOT
            or configuration is None
            or not configuration.is_enabled
            or not settings.openai_api_key
        ):
            return
        existing_run = session.scalar(
            select(AIRun).where(AIRun.input_message_id == input_message.id)
        )
        if existing_run and existing_run.status != AIRunStatus.PENDING:
            return

        retriever = LexicalKnowledgeRetriever(session)
        request = build_ai_request(
            session,
            organization_id=str(input_message.organization_id),
            conversation_id=str(conversation.id),
            question=input_message.body or "",
            retriever=retriever,
        )
        run = existing_run
        if run is None:
            run = AIRun(
                organization_id=input_message.organization_id,
                conversation_id=conversation.id,
                input_message_id=input_message.id,
                status=AIRunStatus.PENDING,
                provider="openai",
                model=settings.openai_model,
                prompt_version=PROMPT_VERSION,
                retrieved_chunk_ids=[item.chunk_id for item in request.knowledge],
            )
            session.add(run)
            session.commit()
            session.refresh(run)
        else:
            run.provider = "openai"
            run.model = settings.openai_model
            run.prompt_version = PROMPT_VERSION
            run.retrieved_chunk_ids = [item.chunk_id for item in request.knowledge]
            session.commit()
            session.refresh(run)
        started_at = time.perf_counter()

        preflight = decide_ai_route(request.knowledge)
        if preflight.route == AIRoute.LOCAL:
            output_message = Message(
                organization_id=input_message.organization_id,
                conversation_id=conversation.id,
                direction=MessageDirection.OUTBOUND,
                message_type=MessageType.TEXT,
                status=MessageStatus.QUEUED,
                body="\n".join(item.content for item in request.knowledge),
                raw_payload={
                    "ai_run_id": str(run.id),
                    "local_response": True,
                    "reason": preflight.reason,
                    "source_titles": list(
                        dict.fromkeys(item.source_title for item in request.knowledge)
                    ),
                },
            )
            session.add(output_message)
            session.flush()
            run.output_message_id = output_message.id
            run.status = AIRunStatus.COMPLETED
            run.provider = "local"
            run.model = "structured-profile-v1"
            run.confidence = 100
            run.latency_ms = int((time.perf_counter() - started_at) * 1000)
            run.input_tokens = 0
            run.output_tokens = 0
            session.commit()
            enqueue_outbound_message(str(output_message.id))
            return

        if preflight.route == AIRoute.HANDOFF:
            output_message = Message(
                organization_id=input_message.organization_id,
                conversation_id=conversation.id,
                direction=MessageDirection.OUTBOUND,
                message_type=MessageType.TEXT,
                status=MessageStatus.QUEUED,
                body=configuration.fallback_message,
                raw_payload={
                    "ai_run_id": str(run.id),
                    "fallback": True,
                    "reason": preflight.reason,
                },
            )
            session.add(output_message)
            session.flush()
            conversation.mode = ConversationMode.HUMAN
            assign_conversation_if_needed(session, conversation)
            run.output_message_id = output_message.id
            run.status = AIRunStatus.ESCALATED
            run.provider = "local"
            run.model = "knowledge-preflight-v1"
            run.confidence = 0
            run.latency_ms = int((time.perf_counter() - started_at) * 1000)
            run.input_tokens = 0
            run.output_tokens = 0
            session.commit()
            enqueue_outbound_message(str(output_message.id))
            return

        subscription = session.scalar(
            select(Subscription).where(
                Subscription.organization_id == input_message.organization_id
            )
        )
        daily_limit = subscription.ai_daily_request_limit if subscription else 0
        daily_token_limit = subscription.ai_daily_token_limit if subscription else 0
        token_reservation = estimate_token_reservation(
            request,
            max_output_tokens=DEFAULT_MAX_OUTPUT_TOKENS,
        )
        if not reserve_paid_ai_request(
            session,
            organization_id=input_message.organization_id,
            daily_limit=daily_limit,
            daily_token_limit=daily_token_limit,
            token_reservation=token_reservation,
        ):
            quota_decision = decide_ai_route(request.knowledge, quota_available=False)
            output_message = Message(
                organization_id=input_message.organization_id,
                conversation_id=conversation.id,
                direction=MessageDirection.OUTBOUND,
                message_type=MessageType.TEXT,
                status=MessageStatus.QUEUED,
                body=configuration.fallback_message,
                raw_payload={
                    "ai_run_id": str(run.id),
                    "fallback": True,
                    "reason": quota_decision.reason,
                },
            )
            session.add(output_message)
            session.flush()
            conversation.mode = ConversationMode.HUMAN
            assign_conversation_if_needed(session, conversation)
            run.output_message_id = output_message.id
            run.status = AIRunStatus.ESCALATED
            run.provider = "local"
            run.model = "usage-limit-v1"
            run.confidence = 0
            run.latency_ms = int((time.perf_counter() - started_at) * 1000)
            run.input_tokens = 0
            run.output_tokens = 0
            session.commit()
            enqueue_outbound_message(str(output_message.id))
            return
        session.commit()

        try:
            provider = OpenAIResponsesProvider(
                api_key=settings.openai_api_key,
                model=settings.openai_model,
            )
            result = provider.generate(request)
            should_handoff = (
                result.should_handoff
                or result.confidence < configuration.minimum_confidence
            )
            body = configuration.fallback_message if should_handoff else result.content
            cited_source_ids = set(result.source_ids)
            source_titles = list(
                dict.fromkeys(
                    item.source_title
                    for item in request.knowledge
                    if item.chunk_id in cited_source_ids
                )
            )
            output_message = Message(
                organization_id=input_message.organization_id,
                conversation_id=conversation.id,
                direction=MessageDirection.OUTBOUND,
                message_type=MessageType.TEXT,
                status=MessageStatus.QUEUED,
                body=body,
                raw_payload={
                    "ai_run_id": str(run.id),
                    "source_ids": list(result.source_ids),
                    "source_titles": source_titles,
                },
            )
            session.add(output_message)
            session.flush()
            if should_handoff:
                conversation.mode = ConversationMode.HUMAN
                assign_conversation_if_needed(session, conversation)
            run.output_message_id = output_message.id
            run.status = AIRunStatus.ESCALATED if should_handoff else AIRunStatus.COMPLETED
            run.provider = result.provider
            run.model = result.model
            run.confidence = result.confidence
            run.latency_ms = int((time.perf_counter() - started_at) * 1000)
            run.input_tokens = result.input_tokens
            run.output_tokens = result.output_tokens
            record_paid_ai_tokens(
                session,
                organization_id=input_message.organization_id,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                token_reservation=token_reservation,
            )
            session.commit()
            enqueue_outbound_message(str(output_message.id))
        except Exception as exc:  # noqa: BLE001 - provider and network failures share fallback
            session.rollback()
            failed_run = session.get(AIRun, run.id)
            failed_conversation = session.get(Conversation, conversation.id)
            if failed_run and failed_conversation:
                release_ai_token_reservation(
                    session,
                    organization_id=input_message.organization_id,
                    token_reservation=token_reservation,
                )
                failed_run.status = AIRunStatus.FAILED
                failed_run.error = safe_ai_error_code(exc)
                failed_run.latency_ms = int((time.perf_counter() - started_at) * 1000)
                failed_conversation.mode = ConversationMode.HUMAN
                assign_conversation_if_needed(session, failed_conversation)
                fallback = Message(
                    organization_id=input_message.organization_id,
                    conversation_id=conversation.id,
                    direction=MessageDirection.OUTBOUND,
                    message_type=MessageType.TEXT,
                    status=MessageStatus.QUEUED,
                    body=configuration.fallback_message,
                    raw_payload={"ai_run_id": str(run.id), "fallback": True},
                )
                session.add(fallback)
                session.flush()
                failed_run.output_message_id = fallback.id
                session.commit()
                enqueue_outbound_message(str(fallback.id))
