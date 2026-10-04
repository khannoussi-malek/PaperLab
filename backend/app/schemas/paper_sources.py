from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, SecretStr, StringConstraints, create_model

from app.core.source_registry import KEYED_IDS, SOURCE_IDS

# The same ids, in the same order, as app.core.source_registry.SOURCE_IDS.
SourceId = Literal[*SOURCE_IDS]


class PaperSourceOut(BaseModel):
    """Never a key: `has_key` (null for a source that takes none) and `key_hint` (last 4 characters; null under 8)."""

    model_config = ConfigDict(from_attributes=True)

    id: SourceId
    name: str
    enabled: bool
    has_key: bool | None
    key_hint: str | None


class PaperSourcesOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    contact_email: str | None
    sources: list[PaperSourceOut]


# Only the sources sent change (a missing source keeps its switch); not Optional, so a sent null is a 422. One
# bool field per registry source — adding a source needs no change here.
SourceSwitches = create_model(
    "SourceSwitches", __config__=ConfigDict(extra="forbid"), **{source: (bool, None) for source in SOURCE_IDS}
)

# A missing source keeps its key, null removes it. SecretStr keeps keys out of reprs and tracebacks; the key rules
# are checked in core, whose messages never quote a key. One field per keyed registry source.
SourceKeys = create_model(
    "SourceKeys", __config__=ConfigDict(extra="forbid"),
    **{source: (SecretStr | None, None) for source in KEYED_IDS},
)  # fmt: skip


class PaperSourcesUpdate(BaseModel):
    """Only the fields sent change: a missing contact_email keeps it, null removes it."""

    model_config = ConfigDict(extra="forbid")

    # The format and 254-character rules are core's; this only caps what is read.
    contact_email: Annotated[str, StringConstraints(max_length=1000)] | None = None
    enabled: SourceSwitches = None
    api_keys: SourceKeys = None
