from fastapi import APIRouter
from sqlalchemy import func, select

from app.api.dependencies import CurrentUser, DatabaseSession
from app.models.core import (
    Conversation,
    ConversationMode,
    ConversationStatus,
    Message,
    MessageDirection,
    MessageStatus,
)
from app.schemas.notification import NotificationSummaryResponse

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("/summary", response_model=NotificationSummaryResponse)
def get_notification_summary(
    session: DatabaseSession, current_user: CurrentUser
) -> NotificationSummaryResponse:
    base = [
        Conversation.organization_id == current_user.organization_id,
        Conversation.status != ConversationStatus.CLOSED,
    ]
    total_unread = session.scalar(
        select(func.coalesce(func.sum(Conversation.unread_count), 0)).where(*base)
    )
    human_unread = session.scalar(
        select(func.coalesce(func.sum(Conversation.unread_count), 0)).where(
            *base, Conversation.mode == ConversationMode.HUMAN
        )
    )
    waiting_human = session.scalar(
        select(func.count(Conversation.id)).where(
            *base, Conversation.mode == ConversationMode.HUMAN
        )
    )
    failed_outbound = session.scalar(
        select(func.count(Message.id)).where(
            Message.organization_id == current_user.organization_id,
            Message.direction == MessageDirection.OUTBOUND,
            Message.status == MessageStatus.FAILED,
        )
    )
    return NotificationSummaryResponse(
        total_unread=int(total_unread or 0),
        human_unread=int(human_unread or 0),
        waiting_human=int(waiting_human or 0),
        failed_outbound=int(failed_outbound or 0),
    )
