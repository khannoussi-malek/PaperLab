from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, SecretStr, StringConstraints

# The same ids, in the same order, as app.core.paper_sources.SOURCES (tests/test_paper_sources_api.py checks).
SourceId = Literal["openalex", "crossref", "semantic_scholar", "arxiv", "core", "unpaywall"]


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


class SourceSwitches(BaseModel):
    """Only the sources sent change."""

    model_config = ConfigDict(extra="forbid")

    # not Optional: a sent null is a 422, a missing source keeps its switch
    openalex: bool = None
    crossref: bool = None
    semantic_scholar: bool = None
    arxiv: bool = None
    core: bool = None
    unpaywall: bool = None


class SourceKeys(BaseModel):
    """A missing source keeps its key, null removes it. SecretStr keeps keys out of reprs and tracebacks; the key rules
    are checked in core, whose messages never quote a key."""

    model_config = ConfigDict(extra="forbid")

    openalex: SecretStr | None = None
    semantic_scholar: SecretStr | None = None
    core: SecretStr | None = None


class PaperSourcesUpdate(BaseModel):
    """Only the fields sent change: a missing contact_email keeps it, null removes it."""

    model_config = ConfigDict(extra="forbid")

    # The format and 254-character rules are core's; this only caps what is read.
    contact_email: Annotated[str, StringConstraints(max_length=1000)] | None = None
    enabled: SourceSwitches = None
    api_keys: SourceKeys = None
