import uuid
from datetime import UTC, datetime

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.core import AIUsageDaily


def ai_quota_status(used: int, limit: int) -> tuple[int, str]:
    if limit <= 0:
        return 100, "exhausted"
    percentage = min(100, round(used / limit * 100))
    if used >= limit:
        return percentage, "exhausted"
    if percentage >= 80:
        return percentage, "warning"
    return percentage, "normal"


def reserve_paid_ai_request(
    session: Session, *, organization_id: uuid.UUID, daily_limit: int
) -> bool:
    """Atomically reserve one paid provider request for the current UTC day."""
    if daily_limit <= 0:
        return False
    today = datetime.now(UTC).date()
    statement = (
        insert(AIUsageDaily)
        .values(
            organization_id=organization_id,
            usage_date=today,
            request_count=1,
        )
        .on_conflict_do_update(
            index_elements=[
                AIUsageDaily.organization_id,
                AIUsageDaily.usage_date,
            ],
            set_={
                "request_count": AIUsageDaily.request_count + 1,
                "updated_at": datetime.now(UTC),
            },
            where=AIUsageDaily.request_count < daily_limit,
        )
        .returning(AIUsageDaily.request_count)
    )
    return session.scalar(statement) is not None


def record_paid_ai_tokens(
    session: Session,
    *,
    organization_id: uuid.UUID,
    input_tokens: int | None,
    output_tokens: int | None,
) -> None:
    session.execute(
        update(AIUsageDaily)
        .where(
            AIUsageDaily.organization_id == organization_id,
            AIUsageDaily.usage_date == datetime.now(UTC).date(),
        )
        .values(
            input_tokens=AIUsageDaily.input_tokens + max(0, input_tokens or 0),
            output_tokens=AIUsageDaily.output_tokens + max(0, output_tokens or 0),
            updated_at=datetime.now(UTC),
        )
    )
