from pydantic import BaseModel


class OnboardingStepResponse(BaseModel):
    key: str
    title: str
    description: str
    section: str
    completed: bool
    required: bool


class OnboardingResponse(BaseModel):
    completed_required: int
    total_required: int
    progress_percent: int
    is_complete: bool
    steps: list[OnboardingStepResponse]
