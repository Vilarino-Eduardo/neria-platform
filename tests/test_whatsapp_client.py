from unittest.mock import patch

from app.integrations.whatsapp.client import MetaWhatsAppClient
from app.tasks.whatsapp import enqueue_outbound_message


def test_enqueue_failure_leaves_message_for_periodic_recovery() -> None:
    with patch(
        "app.tasks.whatsapp.send_whatsapp_message.delay",
        side_effect=ConnectionError("broker unavailable"),
    ):
        assert enqueue_outbound_message("message-id") is False


def test_build_media_and_interactive_payloads() -> None:
    document = MetaWhatsAppClient.build_content(
        message_type="document",
        body="Seu documento",
        media_url="https://example.com/file.pdf",
        media_filename="file.pdf",
        interactive=None,
    )
    assert document == {
        "link": "https://example.com/file.pdf",
        "caption": "Seu documento",
        "filename": "file.pdf",
    }

    buttons = MetaWhatsAppClient.build_content(
        message_type="interactive",
        body=None,
        media_url=None,
        media_filename=None,
        interactive={
            "kind": "buttons",
            "body": "Escolha",
            "footer": "Neria",
            "buttons": [{"id": "menu", "title": "Menu"}],
        },
    )
    assert buttons["type"] == "button"
    assert buttons["action"]["buttons"][0]["reply"]["id"] == "menu"

    list_message = MetaWhatsAppClient.build_content(
        message_type="interactive",
        body=None,
        media_url=None,
        media_filename=None,
        interactive={
            "kind": "list",
            "body": "Escolha um documento",
            "button_text": "Ver opções",
            "sections": [
                {
                    "title": "Documentos",
                    "rows": [{"id": "doc-1", "title": "Contrato", "description": None}],
                }
            ],
        },
    )
    assert list_message["type"] == "list"
    assert list_message["action"]["sections"][0]["rows"][0] == {
        "id": "doc-1",
        "title": "Contrato",
    }

    template = MetaWhatsAppClient.build_content(
        message_type="template",
        body=None,
        media_url=None,
        media_filename=None,
        interactive=None,
        template={
            "name": "retomar_atendimento",
            "language": "pt_BR",
            "parameters": ["Cliente"],
        },
    )
    assert template["name"] == "retomar_atendimento"
    assert template["components"][0]["parameters"][0]["text"] == "Cliente"
