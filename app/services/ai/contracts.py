from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class RetrievedKnowledge:
    chunk_id: str
    source_title: str
    content: str
    score: float


@dataclass(frozen=True)
class AIMessage:
    role: str
    content: str


@dataclass(frozen=True)
class AIRequest:
    system_instructions: str
    messages: list[AIMessage]
    knowledge: list[RetrievedKnowledge] = field(default_factory=list)


@dataclass(frozen=True)
class AIResult:
    content: str
    confidence: int
    provider: str
    model: str
    should_handoff: bool = False
    source_ids: tuple[str, ...] = ()
    input_tokens: int | None = None
    output_tokens: int | None = None


class AIProvider(Protocol):
    def generate(self, request: AIRequest) -> AIResult: ...


class KnowledgeRetriever(Protocol):
    def search(self, organization_id: str, query: str, limit: int) -> list[RetrievedKnowledge]: ...
