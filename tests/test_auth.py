import uuid
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.auth import resolve_client_ip
from app.application import app
from app.database.session import SessionLocal
from app.models.core import Organization

client = TestClient(app)


def test_registration_rejects_common_and_repetitive_passwords() -> None:
    suffix = uuid.uuid4().hex[:10]
    base_payload = {
        "organization_name": "Empresa senha",
        "organization_slug": f"senha-{suffix}",
        "admin_name": "Administrador",
        "admin_email": f"senha-{suffix}@example.com",
    }

    common = client.post(
        "/api/v1/auth/register",
        json={**base_payload, "password": "123456789012"},
    )
    repetitive = client.post(
        "/api/v1/auth/register",
        json={**base_payload, "password": "aaaaaaaaaaaa"},
    )

    assert common.status_code == 422
    assert repetitive.status_code == 422


def test_concurrent_registration_conflict_returns_409() -> None:
    suffix = uuid.uuid4().hex[:10]
    with patch.object(
        Session,
        "commit",
        side_effect=IntegrityError("INSERT", {}, Exception("unique violation")),
    ):
        response = client.post(
            "/api/v1/auth/register",
            json={
                "organization_name": "Empresa concorrente",
                "organization_slug": f"concorrente-{suffix}",
                "admin_name": "Administrador",
                "admin_email": f"concorrente-{suffix}@example.com",
                "password": "senha-segura-123",
            },
        )

    assert response.status_code == 409
    assert response.json()["detail"] == "Empresa ou e-mail já cadastrado."


def test_client_ip_only_trusts_forwarding_from_configured_proxies() -> None:
    assert resolve_client_ip("198.51.100.8", "203.0.113.40", "10.0.0.0/8") == "198.51.100.8"
    assert resolve_client_ip("10.0.0.5", "203.0.113.40", "10.0.0.0/8") == "203.0.113.40"
    assert (
        resolve_client_ip(
            "10.0.0.5",
            "203.0.113.40, 192.168.1.8",
            "10.0.0.0/8,192.168.0.0/16",
        )
        == "203.0.113.40"
    )
    assert resolve_client_ip("10.0.0.5", "not-an-ip", "10.0.0.0/8") == "10.0.0.5"


def test_registration_is_rate_limited_by_ip() -> None:
    suffix = uuid.uuid4().hex[:10]
    with (
        patch("app.api.auth.retry_after", return_value=37),
        patch("app.api.auth.record_attempt") as record,
    ):
        response = client.post(
            "/api/v1/auth/register",
            json={
                "organization_name": "Empresa limitada",
                "organization_slug": f"limitada-{suffix}",
                "admin_name": "Administrador",
                "admin_email": f"limitada-{suffix}@example.com",
                "password": "senha-segura-123",
            },
        )

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "37"
    record.assert_not_called()


def test_registration_login_and_user_limit() -> None:
    suffix = uuid.uuid4().hex[:10]
    slug = f"empresa-{suffix}"
    admin_email = f"admin-{suffix}@example.com"
    password = "senha-segura-123"
    organization_id = None

    try:
        registration = client.post(
            "/api/v1/auth/register",
            json={
                "organization_name": "Empresa Teste",
                "organization_slug": slug,
                "admin_name": "Administrador",
                "admin_email": admin_email,
                "password": password,
            },
        )
        assert registration.status_code == 201
        organization_id = registration.json()["organization"]["id"]

        login = client.post(
            "/api/v1/auth/login",
            json={"email": admin_email, "password": password},
        )
        assert login.status_code == 200
        assert login.cookies.get("neria_session") == login.json()["access_token"]
        csrf_token = login.cookies.get("neria_csrf")
        assert csrf_token
        assert "httponly" in login.headers["set-cookie"].lower()
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        current_user = client.get("/api/v1/auth/me", headers=headers)
        assert current_user.status_code == 200
        assert current_user.json()["role"] == "admin"
        assert client.get("/api/v1/auth/me").status_code == 200

        refused_logout = client.post("/api/v1/auth/logout")
        assert refused_logout.status_code == 403
        logout = client.post(
            "/api/v1/auth/logout", headers={"X-CSRF-Token": csrf_token}
        )
        assert logout.status_code == 204
        assert client.get("/api/v1/auth/me").status_code == 401
        login = client.post(
            "/api/v1/auth/login",
            json={"email": admin_email, "password": password},
        )
        assert login.status_code == 200
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        subscription = client.get("/api/v1/billing/subscription", headers=headers)
        assert subscription.status_code == 200
        assert subscription.json()["status"] == "trialing"
        assert subscription.json()["max_users"] == 3

        initial_onboarding = client.get("/api/v1/onboarding", headers=headers)
        assert initial_onboarding.status_code == 200
        assert initial_onboarding.json()["completed_required"] == 0
        assert initial_onboarding.json()["total_required"] == 4

        dashboard = client.get("/api/v1/dashboard", headers=headers)
        assert dashboard.status_code == 200
        assert dashboard.json()["open_conversations"] == 0
        assert dashboard.json()["messages_today"] == 0
        assert len(dashboard.json()["daily_volume"]) == 7

        with patch("app.api.auth.send_password_reset_email") as send_reset_email:
            recovery = client.post(
                "/api/v1/auth/forgot-password", json={"email": admin_email}
            )
        assert recovery.status_code == 200
        reset_url = send_reset_email.call_args.args[1]
        reset_token = reset_url.split("reset_token=", 1)[1]
        new_password = "nova-senha-segura-456"
        reset = client.post(
            "/api/v1/auth/reset-password",
            json={"token": reset_token, "password": new_password},
        )
        assert reset.status_code == 200
        expired_session = client.get("/api/v1/auth/me", headers=headers)
        assert expired_session.status_code == 401
        reused = client.post(
            "/api/v1/auth/reset-password",
            json={"token": reset_token, "password": "outra-senha-789"},
        )
        assert reused.status_code == 400
        new_login = client.post(
            "/api/v1/auth/login",
            json={"email": admin_email, "password": new_password},
        )
        assert new_login.status_code == 200
        headers = {"Authorization": f"Bearer {new_login.json()['access_token']}"}

        with patch("app.api.auth.send_password_reset_email") as unknown_email:
            unknown_recovery = client.post(
                "/api/v1/auth/forgot-password",
                json={"email": f"unknown-{suffix}@example.com"},
            )
        assert unknown_recovery.status_code == 200
        unknown_email.assert_not_called()

        profile = client.patch(
            "/api/v1/organization/profile",
            headers=headers,
            json={
                "company_name": "Empresa Atualizada",
                "welcome_message": "Olá! Como podemos ajudar?",
                "primary_color": "#123ABC",
                "description": "Empresa usada para validar o onboarding.",
                "contact_email": admin_email,
                "opening_hours": "Segunda a sexta, das 8h às 18h.",
            },
        )
        assert profile.status_code == 200
        assert profile.json()["company_name"] == "Empresa Atualizada"

        onboarding_after_profile = client.get("/api/v1/onboarding", headers=headers)
        assert onboarding_after_profile.status_code == 200
        assert onboarding_after_profile.json()["completed_required"] == 1

        created_user_ids = []
        for index in range(2):
            response = client.post(
                "/api/v1/users",
                headers=headers,
                json={
                    "name": f"Atendente {index}",
                    "email": f"agent-{index}-{suffix}@example.com",
                    "password": password,
                },
            )
            assert response.status_code == 201
            assert response.json()["role"] == "agent"
            created_user_ids.append(response.json()["id"])

        users = client.get("/api/v1/users", headers=headers)
        assert users.status_code == 200
        assert len(users.json()) == 3

        quick_reply = client.post(
            "/api/v1/quick-replies",
            headers=headers,
            json={
                "title": "Horário de atendimento",
                "shortcut": "horario",
                "content": "Atendemos de segunda a sexta, das 8h às 18h.",
            },
        )
        assert quick_reply.status_code == 201
        listed_replies = client.get("/api/v1/quick-replies", headers=headers)
        assert listed_replies.status_code == 200
        assert listed_replies.json()[0]["shortcut"] == "horario"
        updated_reply = client.patch(
            f"/api/v1/quick-replies/{quick_reply.json()['id']}",
            headers=headers,
            json={"title": "Nosso horário"},
        )
        assert updated_reply.status_code == 200

        agent_login = client.post(
            "/api/v1/auth/login",
            json={
                "email": f"agent-0-{suffix}@example.com",
                "password": password,
            },
        )
        agent_headers = {"Authorization": f"Bearer {agent_login.json()['access_token']}"}
        forbidden_reply = client.post(
            "/api/v1/quick-replies",
            headers=agent_headers,
            json={"title": "Sem permissão", "shortcut": "negado", "content": "Teste"},
        )
        assert forbidden_reply.status_code == 403

        deleted_reply = client.delete(
            f"/api/v1/quick-replies/{quick_reply.json()['id']}", headers=headers
        )
        assert deleted_reply.status_code == 204
        assert client.get("/api/v1/quick-replies", headers=headers).json() == []

        limit_response = client.post(
            "/api/v1/users",
            headers=headers,
            json={
                "name": "Atendente excedente",
                "email": f"extra-{suffix}@example.com",
                "password": password,
            },
        )
        assert limit_response.status_code == 409
        assert limit_response.json()["detail"] == "Limite de usuários atingido."

        deactivated = client.patch(
            f"/api/v1/users/{created_user_ids[0]}",
            headers=headers,
            json={"is_active": False},
        )
        assert deactivated.status_code == 200
        assert deactivated.json()["is_active"] is False

        replacement = client.post(
            "/api/v1/users",
            headers=headers,
            json={
                "name": "Atendente substituto",
                "email": f"replacement-{suffix}@example.com",
                "password": password,
            },
        )
        assert replacement.status_code == 201

        blocked_email = f"blocked-{suffix}@example.com"
        for _ in range(5):
            failed_login = client.post(
                "/api/v1/auth/login",
                json={"email": blocked_email, "password": "senha-incorreta"},
            )
            assert failed_login.status_code == 401
        rate_limited = client.post(
            "/api/v1/auth/login",
            json={"email": blocked_email, "password": "senha-incorreta"},
        )
        assert rate_limited.status_code == 429
        assert int(rate_limited.headers["Retry-After"]) > 0

        audit_logs = client.get("/api/v1/audit-logs", headers=headers)
        assert audit_logs.status_code == 200
        actions = {item["action"] for item in audit_logs.json()}
        assert "auth.login_succeeded" in actions
        assert "auth.password_reset_completed" in actions
        assert "organization.profile_updated" in actions
        assert "user.created" in actions

        with patch(
            "app.api.billing.get_settings",
            return_value=SimpleNamespace(billing_admin_key="manual-test-key"),
        ):
            suspended = client.patch(
                f"/api/v1/billing/internal/organizations/{organization_id}",
                headers={"X-Billing-Admin-Key": "manual-test-key"},
                json={"status": "suspended", "notes": "Teste de bloqueio"},
            )
        assert suspended.status_code == 200
        assert suspended.json()["status"] == "suspended"
        blocked_access = client.get("/api/v1/users", headers=headers)
        assert blocked_access.status_code == 402
        visible_subscription = client.get("/api/v1/billing/subscription", headers=headers)
        assert visible_subscription.status_code == 200
    finally:
        if organization_id is not None:
            with SessionLocal() as session:
                session.execute(
                    delete(Organization).where(Organization.id == uuid.UUID(organization_id))
                )
                session.commit()
