import logging
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import or_, select, update

from app.database.session import SessionLocal
from app.models.core import KnowledgeSource, KnowledgeSourceStatus
from app.services.knowledge_service import extract_text, process_existing_source
from app.services.object_storage import get_object_storage
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)
MAX_PROCESSING_ATTEMPTS = 5
TEMPORARY_STORAGE_ERROR = (
    "O armazenamento está temporariamente indisponível. "
    "Uma nova tentativa será feita automaticamente."
)
FINAL_STORAGE_ERROR = (
    "O armazenamento permaneceu indisponível. Exclua este item e envie o arquivo novamente."
)


def record_storage_failure(session, source_id: uuid.UUID) -> None:
    session.rollback()
    source = session.get(KnowledgeSource, source_id)
    if source is None:
        return
    source.processing_claimed_at = None
    if source.processing_attempts >= MAX_PROCESSING_ATTEMPTS:
        source.status = KnowledgeSourceStatus.FAILED
        source.error = FINAL_STORAGE_ERROR
    else:
        source.status = KnowledgeSourceStatus.PROCESSING
        source.error = TEMPORARY_STORAGE_ERROR
    session.commit()


@celery_app.task(name="knowledge.process_source")
def process_knowledge_source(source_id: str) -> None:
    now = datetime.now(UTC)
    stale_before = now - timedelta(minutes=5)
    with SessionLocal() as session:
        source = session.scalar(
            select(KnowledgeSource)
            .where(
                KnowledgeSource.id == uuid.UUID(source_id),
                KnowledgeSource.status == KnowledgeSourceStatus.PROCESSING,
                KnowledgeSource.processing_attempts < MAX_PROCESSING_ATTEMPTS,
                or_(
                    KnowledgeSource.processing_claimed_at.is_(None),
                    KnowledgeSource.processing_claimed_at < stale_before,
                ),
            )
            .with_for_update(skip_locked=True)
        )
        if source is None or not source.storage_key:
            return
        source.processing_attempts += 1
        source.processing_claimed_at = now
        session.commit()
        try:
            content = get_object_storage().get(source.storage_key)
        except Exception:
            record_storage_failure(session, source.id)
            logger.exception(
                "knowledge_source_storage_unavailable",
                extra={"source_id": source_id},
            )
            return

        try:
            text = extract_text(content, Path(source.storage_key).suffix.lower())
            process_existing_source(session, source, text)
            session.commit()
        except Exception as exc:
            session.rollback()
            failed = session.get(KnowledgeSource, uuid.UUID(source_id))
            if failed:
                failed.status = KnowledgeSourceStatus.FAILED
                failed.processing_claimed_at = None
                failed.error = (
                    str(exc)[:300]
                    if isinstance(exc, ValueError)
                    else "Não foi possível processar o arquivo enviado."
                )
                session.commit()
            logger.exception("knowledge_source_processing_failed", extra={"source_id": source_id})


def enqueue_knowledge_source_processing(source_id: str) -> bool:
    try:
        process_knowledge_source.delay(source_id)
        return True
    except Exception:
        logger.exception("knowledge_source_enqueue_failed", extra={"source_id": source_id})
        return False


@celery_app.task(name="knowledge.recover_processing_sources")
def recover_processing_knowledge_sources() -> int:
    stale_before = datetime.now(UTC) - timedelta(minutes=5)
    with SessionLocal() as session:
        session.execute(
            update(KnowledgeSource)
            .where(
                KnowledgeSource.status == KnowledgeSourceStatus.PROCESSING,
                KnowledgeSource.processing_attempts >= MAX_PROCESSING_ATTEMPTS,
            )
            .values(
                status=KnowledgeSourceStatus.FAILED,
                processing_claimed_at=None,
                error="O processamento falhou após várias tentativas.",
            )
        )
        source_ids = list(
            session.scalars(
                select(KnowledgeSource.id)
                .where(
                    KnowledgeSource.status == KnowledgeSourceStatus.PROCESSING,
                    KnowledgeSource.processing_attempts < MAX_PROCESSING_ATTEMPTS,
                    or_(
                        KnowledgeSource.processing_claimed_at.is_(None),
                        KnowledgeSource.processing_claimed_at < stale_before,
                    ),
                )
                .order_by(KnowledgeSource.created_at)
                .limit(100)
            )
        )
        session.commit()

    dispatched = 0
    for source_id in source_ids:
        if not enqueue_knowledge_source_processing(str(source_id)):
            break
        dispatched += 1
    return dispatched
