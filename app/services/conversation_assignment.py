from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.core import (
    Conversation,
    ConversationEvent,
    ConversationMode,
    ConversationStatus,
    OrganizationProfile,
    User,
)


def assign_conversation_if_needed(
    session: Session, conversation: Conversation
) -> User | None:
    if conversation.assigned_user_id is not None or conversation.mode != ConversationMode.HUMAN:
        return None
    enabled = session.scalar(
        select(OrganizationProfile.auto_assignment_enabled).where(
            OrganizationProfile.organization_id == conversation.organization_id
        )
    )
    if not enabled:
        return None

    open_count = func.count(Conversation.id)
    assignee = session.scalar(
        select(User)
        .outerjoin(
            Conversation,
            (Conversation.assigned_user_id == User.id)
            & (Conversation.status != ConversationStatus.CLOSED),
        )
        .where(
            User.organization_id == conversation.organization_id,
            User.is_active.is_(True),
            User.accepts_assignments.is_(True),
        )
        .group_by(User.id)
        .order_by(open_count, User.created_at, User.id)
        .limit(1)
    )
    if assignee is None:
        return None

    conversation.assigned_user_id = assignee.id
    session.add(
        ConversationEvent(
            organization_id=conversation.organization_id,
            conversation_id=conversation.id,
            event_type="assigned_user_id.changed",
            event_data={"from": None, "to": str(assignee.id), "automatic": True},
        )
    )
    return assignee
