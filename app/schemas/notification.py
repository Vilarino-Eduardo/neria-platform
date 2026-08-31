from pydantic import BaseModel


class NotificationSummaryResponse(BaseModel):
    total_unread: int
    human_unread: int
    waiting_human: int
    failed_outbound: int
