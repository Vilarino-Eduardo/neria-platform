from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta

from fastapi import APIRouter
from sqlalchemy import distinct, func, select

from app.api.dependencies import CurrentUser, DatabaseSession
from app.models.core import (
    Conversation,
    ConversationMode,
    ConversationStatus,
    Message,
    MessageDirection,
    OrganizationProfile,
    User,
)
from app.schemas.dashboard import DailyVolumeResponse, DashboardResponse

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardResponse)
def get_dashboard(
    session: DatabaseSession, current_user: CurrentUser
) -> DashboardResponse:
    organization_id = current_user.organization_id
    now = datetime.now(UTC)
    today_start = datetime.combine(now.date(), time.min, tzinfo=UTC)
    thirty_days_ago = now - timedelta(days=30)
    seven_days_ago = today_start - timedelta(days=6)

    open_conversations = session.scalar(
        select(func.count(Conversation.id)).where(
            Conversation.organization_id == organization_id,
            Conversation.status != ConversationStatus.CLOSED,
        )
    ) or 0
    waiting_human = session.scalar(
        select(func.count(Conversation.id)).where(
            Conversation.organization_id == organization_id,
            Conversation.status != ConversationStatus.CLOSED,
            Conversation.mode == ConversationMode.HUMAN,
        )
    ) or 0
    sla_minutes = session.scalar(
        select(OrganizationProfile.sla_first_response_minutes).where(
            OrganizationProfile.organization_id == organization_id
        )
    ) or 15
    sla_overdue = session.scalar(
        select(func.count(Conversation.id)).where(
            Conversation.organization_id == organization_id,
            Conversation.status != ConversationStatus.CLOSED,
            Conversation.mode == ConversationMode.HUMAN,
            Conversation.last_customer_message_at.is_not(None),
            Conversation.last_customer_message_at <= now - timedelta(minutes=sla_minutes),
            (
                Conversation.last_human_response_at.is_(None)
                | (Conversation.last_human_response_at < Conversation.last_customer_message_at)
            ),
        )
    ) or 0
    messages_today = session.scalar(
        select(func.count(Message.id)).where(
            Message.organization_id == organization_id,
            Message.created_at >= today_start,
        )
    ) or 0
    active_contacts = session.scalar(
        select(func.count(distinct(Conversation.contact_id))).where(
            Conversation.organization_id == organization_id,
            Conversation.last_message_at >= thirty_days_ago,
        )
    ) or 0
    closed_conversations = session.scalar(
        select(func.count(Conversation.id)).where(
            Conversation.organization_id == organization_id,
            Conversation.closed_at >= thirty_days_ago,
        )
    ) or 0

    message_rows = session.execute(
        select(
            Message.conversation_id,
            Message.direction,
            Message.created_at,
            Message.sender_user_id,
        )
        .where(
            Message.organization_id == organization_id,
            Message.created_at >= thirty_days_ago,
        )
        .order_by(Message.conversation_id, Message.created_at)
        .limit(10000)
    )
    pending_inbound: dict = {}
    team_pending_inbound: dict = {}
    response_seconds: list[float] = []
    response_seconds_by_user: dict = defaultdict(list)
    for conversation_id, direction, created_at, sender_user_id in message_rows:
        if direction == MessageDirection.INBOUND:
            pending_inbound.setdefault(conversation_id, created_at)
            team_pending_inbound.setdefault(conversation_id, created_at)
        elif conversation_id in pending_inbound:
            response_seconds.append(
                (created_at - pending_inbound.pop(conversation_id)).total_seconds()
            )
        if sender_user_id is not None and conversation_id in team_pending_inbound:
            response_seconds_by_user[sender_user_id].append(
                (created_at - team_pending_inbound.pop(conversation_id)).total_seconds()
            )

    open_by_user = {
        user_id: count
        for user_id, count in session.execute(
            select(Conversation.assigned_user_id, func.count(Conversation.id))
            .where(
                Conversation.organization_id == organization_id,
                Conversation.status != ConversationStatus.CLOSED,
                Conversation.assigned_user_id.is_not(None),
            )
            .group_by(Conversation.assigned_user_id)
        )
    }
    closed_by_user = {
        user_id: count
        for user_id, count in session.execute(
            select(Conversation.assigned_user_id, func.count(Conversation.id))
            .where(
                Conversation.organization_id == organization_id,
                Conversation.closed_at >= thirty_days_ago,
                Conversation.assigned_user_id.is_not(None),
            )
            .group_by(Conversation.assigned_user_id)
        )
    }
    sent_by_user = {
        user_id: count
        for user_id, count in session.execute(
            select(Message.sender_user_id, func.count(Message.id))
            .where(
                Message.organization_id == organization_id,
                Message.created_at >= thirty_days_ago,
                Message.sender_user_id.is_not(None),
            )
            .group_by(Message.sender_user_id)
        )
    }
    users = session.scalars(
        select(User).where(User.organization_id == organization_id).order_by(User.name)
    )
    team_performance = []
    for user in users:
        user_response_seconds = response_seconds_by_user[user.id]
        team_performance.append(
            {
                "user_id": user.id,
                "name": user.name,
                "role": user.role,
                "is_active": user.is_active,
                "open_assigned": open_by_user.get(user.id, 0),
                "closed_30d": closed_by_user.get(user.id, 0),
                "messages_sent_30d": sent_by_user.get(user.id, 0),
                "average_response_minutes": round(
                    sum(user_response_seconds) / len(user_response_seconds) / 60, 1
                )
                if user_response_seconds
                else None,
            }
        )

    volume: dict[date, dict[str, int]] = defaultdict(
        lambda: {"inbound": 0, "outbound": 0}
    )
    daily_rows = session.execute(
        select(
            func.date(Message.created_at).label("day"),
            Message.direction,
            func.count(Message.id),
        )
        .where(
            Message.organization_id == organization_id,
            Message.created_at >= seven_days_ago,
        )
        .group_by(func.date(Message.created_at), Message.direction)
    )
    for day, direction, count in daily_rows:
        volume[day][direction.value] = count
    daily_volume = [
        DailyVolumeResponse(
            date=(today_start + timedelta(days=offset)).date(),
            **volume[(today_start + timedelta(days=offset)).date()],
        )
        for offset in range(-6, 1)
    ]
    average_minutes = (
        round(sum(response_seconds) / len(response_seconds) / 60, 1)
        if response_seconds
        else None
    )
    return DashboardResponse(
        open_conversations=open_conversations,
        waiting_human=waiting_human,
        messages_today=messages_today,
        active_contacts_30d=active_contacts,
        closed_conversations_30d=closed_conversations,
        average_first_response_minutes=average_minutes,
        sla_overdue=sla_overdue,
        daily_volume=daily_volume,
        team_performance=team_performance,
    )
