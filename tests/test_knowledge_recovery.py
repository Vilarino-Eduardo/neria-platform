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
