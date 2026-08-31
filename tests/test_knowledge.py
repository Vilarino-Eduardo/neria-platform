import uuid

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.application import app
from app.database.session import SessionLocal
from app.models.core import Organization

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
        assert uploaded.status_code == 201
        assert uploaded.json()["filename"] == "horarios.txt"

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
