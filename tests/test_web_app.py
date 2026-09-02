from fastapi.testclient import TestClient

from app.application import app

client = TestClient(app)


def test_web_application_is_served() -> None:
    response = client.get("/app")

    assert response.status_code == 200
    assert "Neria — Atendimento" in response.text
    assert "Base de conhecimento" in response.text
    assert "Criar uma empresa na Neria" in response.text
    assert 'id="registration-form"' in response.text
    assert "/static/app.js?v=" in response.text

    stylesheet = client.get("/static/app.css")
    javascript = client.get("/static/app.js")
    assert stylesheet.status_code == 200
    assert javascript.status_code == 200
    assert "registerOrganization" in javascript.text
    assert "neria_token" not in javascript.text
    assert "Authorization" not in javascript.text
    assert "X-CSRF-Token" in javascript.text
    assert 'minlength="12"' in response.text
    assert "Idempotency-Key" in javascript.text
    assert "E-mail ou senha inválidos." in javascript.text
    assert "Código de suporte" in javascript.text
    assert "displayConversation" in javascript.text
    assert "conversation.status!=='closed'" in javascript.text
    assert "renderKnowledgeEmptyState" in javascript.text
    assert "Selecione uma fonte" in javascript.text
    assert "daily_token_limit" in javascript.text
    assert "daily_token_quota_status" in javascript.text
    assert 'id="ai-version-metrics"' in response.text
    assert "renderAIPromptVersions" in javascript.text
