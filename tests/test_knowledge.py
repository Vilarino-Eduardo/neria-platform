import uuid
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.application import app
from app.database.session import SessionLocal
from app.models.core import KnowledgeSource, KnowledgeSourceStatus, Organization
from app.tasks.knowledge import process_knowledge_source

client = TestClient(app)


def register_organization(suffix: str) -> tuple[uuid.UUID, dict[str, str]]:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": f"Empresa {suffix}",
            "organization_slug": f"knowledge-{suffix}",
            "admin_name": "Administrador",
            "admin_email": f"knowledge-{suffix}@example.com",
            "password": "senha-segura-123",
        },
    )
    assert response.status_code == 201
    return uuid.UUID(response.json()["organization"]["id"]), {
        "Authorization": f"Bearer {response.json()['token']['access_token']}"
    }


def test_manual_and_uploaded_knowledge_are_tenant_scoped() -> None:
    suffix = uuid.uuid4().hex[:10]
    organization_id, headers = register_organization(suffix)
    other_organization_id, other_headers = register_organization(f"other-{suffix}")
    try:
        manual = client.post(
            "/api/v1/knowledge/sources/manual",
            headers=headers,
            json={
                "title": "Política de trocas",
                "content": "Trocas podem ser solicitadas em até sete dias após o recebimento.",
            },
        )
        assert manual.status_code == 201
        assert manual.json()["status"] == "ready"
        assert manual.json()["source_type"] == "manual"

        with patch("app.api.knowledge.enqueue_knowledge_source_processing"):
            uploaded = client.post(
                "/api/v1/knowledge/sources/upload",
                headers=headers,
                data={"title": "Horários de atendimento"},
                files={
                    "file": (
                        "horarios.txt",
                        "Atendemos de segunda a sexta, das nove às dezoito horas.",
                        "text/plain",
                    )
                },
            )
        assert uploaded.status_code == 202
        assert uploaded.json()["filename"] == "horarios.txt"
        assert uploaded.json()["status"] == "processing"
        process_knowledge_source.run(uploaded.json()["id"])
        with SessionLocal() as session:
            processed_upload = session.scalar(
                select(KnowledgeSource).where(KnowledgeSource.id == uploaded.json()["id"])
            )
            assert processed_upload.status == KnowledgeSourceStatus.READY

        sources = client.get("/api/v1/knowledge/sources", headers=headers)
        assert sources.status_code == 200
        assert len(sources.json()) == 2

        chunks = client.get(
            f"/api/v1/knowledge/sources/{manual.json()['id']}/chunks", headers=headers
        )
        assert chunks.status_code == 200
        assert "sete dias" in chunks.json()[0]["content"]

        isolated = client.get(
            f"/api/v1/knowledge/sources/{manual.json()['id']}/chunks",
            headers=other_headers,
        )
        assert isolated.status_code == 404

        removed = client.delete(
            f"/api/v1/knowledge/sources/{uploaded.json()['id']}", headers=headers
        )
        assert removed.status_code == 204
    finally:
        with SessionLocal() as session:
            session.execute(
                delete(Organization).where(
                    Organization.id.in_([organization_id, other_organization_id])
                )
            )
            session.commit()


def test_upload_storage_outage_returns_retryable_error_without_source() -> None:
    suffix = uuid.uuid4().hex[:10]
    organization_id, headers = register_organization(f"storage-{suffix}")
    unavailable_storage = SimpleNamespace(
        put=lambda *_args, **_kwargs: (_ for _ in ()).throw(ConnectionError("offline"))
    )
    try:
        with patch("app.api.knowledge.get_object_storage", return_value=unavailable_storage):
            response = client.post(
                "/api/v1/knowledge/sources/upload",
                headers=headers,
                files={"file": ("documento.txt", "Conteúdo temporário.", "text/plain")},
            )

        assert response.status_code == 503
        assert response.json()["detail"] == "Falha ao armazenar o arquivo."
        with SessionLocal() as session:
            sources = session.scalars(
                select(KnowledgeSource).where(
                    KnowledgeSource.organization_id == organization_id
                )
            ).all()
            assert sources == []
    finally:
        with SessionLocal() as session:
            session.execute(delete(Organization).where(Organization.id == organization_id))
            session.commit()
