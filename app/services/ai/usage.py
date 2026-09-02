import uuid
from datetime import UTC, datetime

from sqlalchemy import func, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.core import AIUsageDaily
from app.services.ai.contracts import AIRequest

TOKEN_ESTIMATE_OVERHEAD = 2_000


def estimate_token_reservation(
    request: AIRequest, *, max_output_tokens: int
) -> int:
    """Reserve conservatively using UTF-8 bytes plus response and protocol overhead."""
    input_bytes = len(request.system_instructions.encode("utf-8"))
    input_bytes += sum(
        len(message.role.encode("utf-8")) + len(message.content.encode("utf-8"))
        for message in request.messages
    )
    input_bytes += sum(
        len(item.source_title.encode("utf-8")) + len(item.content.encode("utf-8"))
        for item in request.knowledge
    )
    return input_bytes + max_output_tokens + TOKEN_ESTIMATE_OVERHEAD


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
    session: Session,
    *,
    organization_id: uuid.UUID,
    daily_limit: int,
    daily_token_limit: int = 100_000_000,
    token_reservation: int = 0,
) -> bool:
    """Atomically reserve one paid provider request for the current UTC day."""
    if (
        daily_limit <= 0
        or daily_token_limit <= 0
        or token_reservation < 0
        or token_reservation > daily_token_limit
    ):
        return False
    today = datetime.now(UTC).date()
    statement = (
        insert(AIUsageDaily)
        .values(
            organization_id=organization_id,
            usage_date=today,
            request_count=1,
            reserved_tokens=token_reservation,
        )
        .on_conflict_do_update(
            index_elements=[
                AIUsageDaily.organization_id,
                AIUsageDaily.usage_date,
            ],
            set_={
                "request_count": AIUsageDaily.request_count + 1,
                "reserved_tokens": AIUsageDaily.reserved_tokens + token_reservation,
                "updated_at": datetime.now(UTC),
            },
            where=(
                (AIUsageDaily.request_count < daily_limit)
                & (
                    AIUsageDaily.input_tokens
                    + AIUsageDaily.output_tokens
                    + AIUsageDaily.reserved_tokens
                    + token_reservation
                    <= daily_token_limit
                )
            ),
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
    token_reservation: int = 0,
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
            reserved_tokens=func.greatest(
                0, AIUsageDaily.reserved_tokens - max(0, token_reservation)
            ),
            updated_at=datetime.now(UTC),
        )
    )


def release_ai_token_reservation(
    session: Session,
    *,
    organization_id: uuid.UUID,
    token_reservation: int,
) -> None:
    session.execute(
        update(AIUsageDaily)
        .where(
            AIUsageDaily.organization_id == organization_id,
            AIUsageDaily.usage_date == datetime.now(UTC).date(),
        )
        .values(
            reserved_tokens=func.greatest(
                0, AIUsageDaily.reserved_tokens - max(0, token_reservation)
            ),
            updated_at=datetime.now(UTC),
        )
    )
