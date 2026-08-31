import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.core import AutomationStatus


class AutomationDefinition(BaseModel):
    start_node_id: str = Field(min_length=1, max_length=100)
    nodes: dict[str, dict[str, Any]]

    @field_validator("nodes")
    @classmethod
    def validate_nodes(cls, nodes: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        if not nodes:
            raise ValueError("A automação precisa ter ao menos um nó.")
        allowed = {"message", "menu", "handoff", "end"}
        for node_id, node in nodes.items():
            if node.get("type") not in allowed:
                raise ValueError(f"Tipo inválido no nó {node_id}.")
            if node.get("type") in {"message", "menu"} and not node.get("text"):
                raise ValueError(f"O nó {node_id} precisa de texto.")
            if node.get("type") == "menu" and not node.get("options"):
                raise ValueError(f"O menu {node_id} precisa de opções.")
        return nodes

    def model_post_init(self, __context: Any, /) -> None:
        if self.start_node_id not in self.nodes:
            raise ValueError("O nó inicial não existe.")
        for node_id, node in self.nodes.items():
            next_ids = []
            if node.get("next_node_id"):
                next_ids.append(node["next_node_id"])
            if node.get("type") == "menu":
                options = node.get("options", [])
                if not 1 <= len(options) <= 3:
                    raise ValueError(f"O menu {node_id} deve ter entre 1 e 3 opções.")
                option_ids = [str(option.get("id", "")).strip() for option in options]
                if any(not value for value in option_ids) or len(option_ids) != len(set(option_ids)):
                    raise ValueError(f"As opções do menu {node_id} precisam de IDs únicos.")
                next_ids.extend(option.get("next_node_id") for option in options)
            if any(next_id not in self.nodes for next_id in next_ids if next_id):
                raise ValueError(f"O nó {node_id} aponta para um nó inexistente.")


class AutomationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    trigger_keywords: list[str] = Field(default_factory=list, max_length=30)
    is_fallback: bool = False
    definition: AutomationDefinition


class AutomationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    trigger_keywords: list[str] | None = Field(default=None, max_length=30)
    is_fallback: bool | None = None
    definition: AutomationDefinition | None = None


class AutomationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    status: AutomationStatus
    version: int
    trigger_keywords: list[str]
    is_fallback: bool
    definition: dict
    created_at: datetime
    updated_at: datetime
