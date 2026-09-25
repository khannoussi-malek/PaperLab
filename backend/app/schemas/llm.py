import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, SecretStr, StringConstraints

Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
ModelName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class ConnectionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["ollama", "anthropic", "openai_compatible"]
    label: Label
    base_url: str | None = None
    # SecretStr keeps the key out of reprs and tracebacks. The key rules (required, refused, empty) are checked in
    # core, whose messages never quote it; the validation handler never echoes request input.
    api_key: SecretStr | None = None


class ConnectionUpdate(BaseModel):
    """Only the fields sent change: a missing api_key keeps the key, null clears it. `kind` can't be sent."""

    model_config = ConfigDict(extra="forbid")

    label: Label = None  # not Optional: a sent null is a 422, a missing label keeps the name
    base_url: str | None = None
    api_key: SecretStr | None = None


class ModelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    is_default: bool


class ConnectionOut(BaseModel):
    """Never a key: `has_key`, and `key_hint` (last 4 characters; null for keys under 8)."""

    id: uuid.UUID
    kind: str
    label: str
    base_url: str | None
    has_key: bool
    key_hint: str | None
    is_local: bool
    models: list[ModelOut]


class ChatModelOut(BaseModel):
    id: uuid.UUID
    name: str
    connection_label: str
    is_local: bool
    is_default: bool


class ConnectionCheckOut(BaseModel):
    ok: bool
    model_count: int | None  # null with ok: the server has no model list
    message: str


class AvailableModelsOut(BaseModel):
    models: list[str] | None  # null: the server has no model list, so names are typed by hand


class ModelCreate(BaseModel):
    name: ModelName


class DefaultModelIn(BaseModel):
    model_id: uuid.UUID


class PullRequest(BaseModel):
    name: ModelName
    # False for Settings → Search's pull of nomic-embed-text (D152): an embedding model never lands in chat's list.
    add_to_chat: bool = True


# SSE payloads of a pull, one model per event name: progress (repeated), then done, or error.
class PullProgressEvent(BaseModel):
    status: str
    total: int | None = None
    completed: int | None = None


class PullDoneEvent(BaseModel):
    model: ModelOut | None  # None: the pull wasn't added to chat (add_to_chat false)


class PullErrorEvent(BaseModel):
    message: str
