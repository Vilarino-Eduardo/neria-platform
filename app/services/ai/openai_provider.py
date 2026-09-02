from openai import OpenAI
from pydantic import BaseModel, Field

from app.services.ai.contracts import AIProvider, AIRequest, AIResult


class OpenAIAnswer(BaseModel):
    answer: str = Field(min_length=1, max_length=4000)
    confidence: int = Field(ge=0, le=100)
    should_handoff: bool


class OpenAIResponsesProvider(AIProvider):
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        max_output_tokens: int = 600,
    ) -> None:
        if not 64 <= max_output_tokens <= 600:
            raise ValueError("max_output_tokens deve estar entre 64 e 600.")
        self.client = OpenAI(api_key=api_key, timeout=30, max_retries=2)
        self.model = model
        self.max_output_tokens = max_output_tokens

    def generate(self, request: AIRequest) -> AIResult:
        knowledge = "\n\n".join(
            f"Fonte: {item.source_title}\n{item.content}" for item in request.knowledge
        )
        instructions = request.system_instructions
        if knowledge:
            instructions += f"\n\nBase de conhecimento recuperada:\n{knowledge}"
        response = self.client.responses.parse(
            model=self.model,
            instructions=instructions,
            input=[
                {"role": message.role, "content": message.content}
                for message in request.messages
            ],
            text_format=OpenAIAnswer,
            reasoning={"effort": "low"},
            store=False,
            max_output_tokens=self.max_output_tokens,
        )
        parsed = response.output_parsed
        if parsed is None:
            raise ValueError("A IA não retornou uma resposta estruturada.")
        usage = response.usage
        return AIResult(
            content=parsed.answer,
            confidence=parsed.confidence,
            should_handoff=parsed.should_handoff,
            provider="openai",
            model=self.model,
            input_tokens=usage.input_tokens if usage else None,
            output_tokens=usage.output_tokens if usage else None,
        )
