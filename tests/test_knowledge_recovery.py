import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import delete

from app.database.session import SessionLocal
from app.models.core import (
    KnowledgeSource,
    KnowledgeSourceStatus,
    KnowledgeSourceType,
    Organization,
)
from app.tasks.knowledge import (
    FINAL_STORAGE_ERROR,
    MAX_PROCESSING_ATTEMPTS,
    TEMPORARY_STORAGE_ERROR,
    process_knowledge_source,
    recover_processing_knowledge_sources,
)


def create_processing_source() -> tuple[uuid.UUID, uuid.UUID]:
    suffix = uuid.uuid4().hex
    organization_id = uuid.uuid4()
    source_id = uuid.uuid4()
    with SessionLocal() as session:
        session.add(
            Organization(
                id=organization_id,
                name="Base em processamento",
                slug=f"knowledge-processing-{suffix}",
            )
        )
        session.flush()
        session.add(
            KnowledgeSource(
                id=source_id,
                organization_id=organization_id,
                title="Documento",
                source_type=KnowledgeSourceType.FILE,
                status=KnowledgeSourceStatus.PROCESSING,
                filename="documento.txt",
                storage_key=f"{organization_id}/documento.txt",
            )
        )
        session.commit()
    return organization_id, source_id


def test_processing_claim_prevents_duplicate_work() -> None:
    organization_id, source_id = create_processing_source()
    storage = SimpleNamespace(get=lambda _key: b"Conteudo suficiente para processar a base.")
    try:
        with patch("app.tasks.knowledge.get_object_storage", return_value=storage):
            process_knowledge_source.run(str(source_id))
            process_knowledge_source.run(str(source_id))

        with SessionLocal() as session:
            source = session.get(KnowledgeSource, source_id)
            assert source.status == KnowledgeSourceStatus.READY
            assert source.processing_attempts == 1
            assert source.processing_claimed_at is None
    finally:
        with SessionLocal() as session:
            session.execute(delete(Organization).where(Organization.id == organization_id))
            session.commit()


def test_interrupted_processing_is_recovered() -> None:
    organization_id, source_id = create_processing_source()
    try:
        with SessionLocal() as session:
            source = session.get(KnowledgeSource, source_id)
            source.processing_attempts = 1
            source.processing_claimed_at = datetime.now(UTC) - timedelta(minutes=10)
            session.commit()

        with patch("app.tasks.knowledge.process_knowledge_source.delay") as dispatch:
            recovered = recover_processing_knowledge_sources.run()

        assert recovered >= 1
        dispatch.assert_any_call(str(source_id))
    finally:
        with SessionLocal() as session:
            session.execute(delete(Organization).where(Organization.id == organization_id))
            session.commit()


def test_storage_outage_is_retried_and_recovers_without_losing_source() -> None:
    organization_id, source_id = create_processing_source()
    unavailable = SimpleNamespace(
        get=lambda _key: (_ for _ in ()).throw(ConnectionError("offline"))
    )
    available = SimpleNamespace(
        get=lambda _key: b"Conteudo restaurado e suficiente para processar a base."
    )
    try:
        with patch("app.tasks.knowledge.get_object_storage", return_value=unavailable):
            process_knowledge_source.run(str(source_id))

        with SessionLocal() as session:
            source = session.get(KnowledgeSource, source_id)
            assert source.status == KnowledgeSourceStatus.PROCESSING
            assert source.processing_attempts == 1
            assert source.processing_claimed_at is None
            assert source.error == TEMPORARY_STORAGE_ERROR

        with patch("app.tasks.knowledge.process_knowledge_source.delay") as dispatch:
            recover_processing_knowledge_sources.run()
        dispatch.assert_any_call(str(source_id))

        with patch("app.tasks.knowledge.get_object_storage", return_value=available):
            process_knowledge_source.run(str(source_id))

        with SessionLocal() as session:
            source = session.get(KnowledgeSource, source_id)
            assert source.status == KnowledgeSourceStatus.READY
            assert source.processing_attempts == 2
            assert source.processing_claimed_at is None
            assert source.error is None
    finally:
        with SessionLocal() as session:
            session.execute(delete(Organization).where(Organization.id == organization_id))
            session.commit()


def test_repeated_storage_outage_becomes_actionable_failure() -> None:
    organization_id, source_id = create_processing_source()
    unavailable = SimpleNamespace(
        get=lambda _key: (_ for _ in ()).throw(ConnectionError("offline"))
    )
    try:
        with patch("app.tasks.knowledge.get_object_storage", return_value=unavailable):
            for _attempt in range(MAX_PROCESSING_ATTEMPTS):
                process_knowledge_source.run(str(source_id))

        with SessionLocal() as session:
            source = session.get(KnowledgeSource, source_id)
            assert source.status == KnowledgeSourceStatus.FAILED
            assert source.processing_attempts == MAX_PROCESSING_ATTEMPTS
            assert source.processing_claimed_at is None
            assert source.error == FINAL_STORAGE_ERROR
    finally:
        with SessionLocal() as session:
            session.execute(delete(Organization).where(Organization.id == organization_id))
            session.commit()
