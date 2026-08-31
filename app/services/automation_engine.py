import re
import unicodedata
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.core import (
    Automation,
    AutomationSession,
    AutomationStatus,
    Conversation,
    ConversationMode,
    Message,
    MessageDirection,
    MessageStatus,
    MessageType,
)
from app.services.conversation_assignment import assign_conversation_if_needed


@dataclass(frozen=True)
class AutomationOutcome:
    handled: bool
    message_ids: list[uuid.UUID]


def normalize_input(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    without_accents = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", without_accents).strip().casefold()


def process_automation(
    session: Session, conversation: Conversation, incoming_body: str | None
) -> AutomationOutcome:
    if conversation.mode != ConversationMode.BOT:
        return AutomationOutcome(handled=False, message_ids=[])

    active_session = session.scalar(
        select(AutomationSession).where(
            AutomationSession.conversation_id == conversation.id,
            AutomationSession.is_active.is_(True),
        )
    )
    automation = None
    node_id = None
    if active_session:
        automation = session.get(Automation, active_session.automation_id)
        if automation and automation.status == AutomationStatus.ACTIVE:
            node_id = resolve_menu_choice(automation, active_session, incoming_body)
        else:
            active_session.is_active = False
            active_session = None

    if automation is None or node_id is None:
        automation = find_triggered_automation(
            session, conversation.organization_id, incoming_body
        )
        if automation is None:
            return AutomationOutcome(handled=False, message_ids=[])
        active_session = session.scalar(
            select(AutomationSession).where(
                AutomationSession.conversation_id == conversation.id
            )
        )
        if active_session is None:
            active_session = AutomationSession(
                organization_id=conversation.organization_id,
                conversation_id=conversation.id,
                automation_id=automation.id,
                automation_version=automation.version,
                current_node_id=automation.definition["start_node_id"],
            )
            session.add(active_session)
        else:
            active_session.automation_id = automation.id
            active_session.automation_version = automation.version
            active_session.current_node_id = automation.definition["start_node_id"]
            active_session.context = {}
            active_session.is_active = True
        node_id = automation.definition["start_node_id"]

    return AutomationOutcome(
        handled=True,
        message_ids=execute_nodes(
            session, conversation, automation, active_session, node_id
        ),
    )


def find_triggered_automation(
    session: Session, organization_id: uuid.UUID, incoming_body: str | None
) -> Automation | None:
    automations = list(
        session.scalars(
            select(Automation).where(
                Automation.organization_id == organization_id,
                Automation.status == AutomationStatus.ACTIVE,
            )
        )
    )
    incoming = normalize_input(incoming_body)
    for automation in automations:
        if any(normalize_input(keyword) == incoming for keyword in automation.trigger_keywords):
            return automation
    return next((automation for automation in automations if automation.is_fallback), None)


def resolve_menu_choice(
    automation: Automation,
    automation_session: AutomationSession,
    incoming_body: str | None,
) -> str | None:
    current_id = automation_session.current_node_id
    current = automation.definition["nodes"].get(current_id or "", {})
    if current.get("type") != "menu":
        return current_id
    incoming = normalize_input(incoming_body)
    for option in current.get("options", []):
        if incoming in {normalize_input(option.get("id")), normalize_input(option.get("title"))}:
            return option.get("next_node_id")
    return current_id


def execute_nodes(
    session: Session,
    conversation: Conversation,
    automation: Automation,
    automation_session: AutomationSession,
    node_id: str,
) -> list[uuid.UUID]:
    message_ids: list[uuid.UUID] = []
    visited: set[str] = set()
    while node_id and node_id not in visited:
        visited.add(node_id)
        node = automation.definition["nodes"][node_id]
        node_type = node["type"]
        if node_type == "message":
            message_ids.append(add_text_message(session, conversation, node["text"]))
            node_id = node.get("next_node_id")
            continue
        if node_type == "menu":
            message_ids.append(add_menu_message(session, conversation, node))
            automation_session.current_node_id = node_id
            break
        if node_type == "handoff":
            if node.get("text"):
                message_ids.append(add_text_message(session, conversation, node["text"]))
            conversation.mode = ConversationMode.HUMAN
            assign_conversation_if_needed(session, conversation)
            automation_session.is_active = False
            break
        if node_type == "end":
            if node.get("text"):
                message_ids.append(add_text_message(session, conversation, node["text"]))
            automation_session.is_active = False
            break
    return message_ids


def add_text_message(session: Session, conversation: Conversation, body: str) -> uuid.UUID:
    message = Message(
        organization_id=conversation.organization_id,
        conversation_id=conversation.id,
        direction=MessageDirection.OUTBOUND,
        message_type=MessageType.TEXT,
        status=MessageStatus.QUEUED,
        body=body,
    )
    session.add(message)
    session.flush()
    return message.id


def add_menu_message(session: Session, conversation: Conversation, node: dict) -> uuid.UUID:
    message = Message(
        organization_id=conversation.organization_id,
        conversation_id=conversation.id,
        direction=MessageDirection.OUTBOUND,
        message_type=MessageType.INTERACTIVE,
        status=MessageStatus.QUEUED,
        body=node["text"],
        raw_payload={
            "interactive": {
                "kind": "buttons",
                "body": node["text"],
                "buttons": [
                    {"id": str(option["id"]), "title": option["title"]}
                    for option in node["options"]
                ],
            }
        },
    )
    session.add(message)
    session.flush()
    return message.id
