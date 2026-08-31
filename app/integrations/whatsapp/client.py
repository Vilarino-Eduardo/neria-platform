from typing import Any

import httpx

from app.core.settings import get_settings


class MetaWhatsAppClient:
    def __init__(self, *, access_token: str, phone_number_id: str) -> None:
        settings = get_settings()
        self.graph_root = f"https://graph.facebook.com/{settings.meta_graph_api_version}"
        self.base_url = f"{self.graph_root}/{phone_number_id}"
        self.headers = {"Authorization": f"Bearer {access_token}"}

    def verify_phone_number(self) -> dict[str, Any]:
        response = httpx.get(
            self.base_url,
            headers=self.headers,
            params={"fields": "display_phone_number,verified_name"},
            timeout=20,
        )
        response.raise_for_status()
        return response.json()

    def list_templates(self, *, business_account_id: str) -> list[dict[str, Any]]:
        response = httpx.get(
            f"{self.graph_root}/{business_account_id}/message_templates",
            headers=self.headers,
            params={"fields": "name,language,status,category", "limit": 250},
            timeout=20,
        )
        response.raise_for_status()
        return response.json().get("data", [])

    def send_message(
        self,
        *,
        recipient: str,
        message_type: str,
        body: str | None = None,
        media_url: str | None = None,
        media_filename: str | None = None,
        interactive: dict | None = None,
        template: dict | None = None,
    ) -> str:
        content = self.build_content(
            message_type=message_type,
            body=body,
            media_url=media_url,
            media_filename=media_filename,
            interactive=interactive,
            template=template,
        )
        response = httpx.post(
            f"{self.base_url}/messages",
            headers=self.headers,
            json={
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": recipient,
                "type": message_type,
                message_type: content,
            },
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        return payload["messages"][0]["id"]

    @staticmethod
    def build_content(
        *,
        message_type: str,
        body: str | None,
        media_url: str | None,
        media_filename: str | None,
        interactive: dict | None,
        template: dict | None = None,
    ) -> dict[str, Any]:
        if message_type == "text":
            return {"preview_url": False, "body": body}
        if message_type in {"image", "audio", "document"}:
            content: dict[str, Any] = {"link": media_url}
            if body and message_type != "audio":
                content["caption"] = body
            if media_filename and message_type == "document":
                content["filename"] = media_filename
            return content
        if message_type == "interactive" and interactive:
            return MetaWhatsAppClient.build_interactive(interactive)
        if message_type == "template" and template:
            content: dict[str, Any] = {
                "name": template["name"],
                "language": {"code": template["language"]},
            }
            parameters = template.get("parameters", [])
            if parameters:
                content["components"] = [
                    {
                        "type": "body",
                        "parameters": [
                            {"type": "text", "text": value} for value in parameters
                        ],
                    }
                ]
            return content
        raise ValueError(f"Tipo de mensagem não suportado: {message_type}")

    @staticmethod
    def build_interactive(content: dict) -> dict[str, Any]:
        result: dict[str, Any] = {
            "body": {"text": content["body"]},
        }
        if content.get("footer"):
            result["footer"] = {"text": content["footer"]}

        if content["kind"] == "buttons":
            result["type"] = "button"
            result["action"] = {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {"id": button["id"], "title": button["title"]},
                    }
                    for button in content["buttons"]
                ]
            }
            return result

        result["type"] = "list"
        result["action"] = {
            "button": content["button_text"],
            "sections": [
                {
                    "title": section["title"],
                    "rows": [
                        {key: value for key, value in row.items() if value is not None}
                        for row in section["rows"]
                    ],
                }
                for section in content["sections"]
            ],
        }
        return result
