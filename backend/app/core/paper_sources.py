"""Which paper sources Find papers and Similar ask, their API keys, and the contact email (M19.5, D74).

One row, `paper_sources`. Until it exists, readers get the defaults: every source on except OpenAlex, the only one that
can cost money (P3). No route returns a key: views carry has_key and key_hint, as model connections do.
"""

import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import InvalidInput
from app.core.llm_connections import key_hint
from app.models import PaperSources

logger = logging.getLogger(__name__)

# Also the trust order when results are merged (D73). Unpaywall only adds PDF links.
SOURCES = ("openalex", "crossref", "semantic_scholar", "arxiv", "core", "unpaywall")
NAMES = {
    "openalex": "OpenAlex", "crossref": "Crossref", "semantic_scholar": "Semantic Scholar", "arxiv": "arXiv",
    "core": "CORE", "unpaywall": "Unpaywall",
}  # fmt: skip
KEYED = ("openalex", "semantic_scholar", "core")
MAX_EMAIL = 254
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

BAD_EMAIL = "Enter an email address like name@example.org."
EMPTY_KEY = "an API key can't be empty; send null to remove it"


@dataclass(frozen=True)
class SourceSettings:
    contact_email: str | None = None
    enabled: Mapping[str, bool] = field(default_factory=lambda: {source: source != "openalex" for source in SOURCES})
    api_keys: Mapping[str, str | None] = field(default_factory=lambda: dict.fromkeys(KEYED))

    @property
    def unpaywall_on(self) -> bool:
        """Unpaywall refuses requests without an email, so its ticked box alone doesn't turn it on."""
        return self.enabled["unpaywall"] and self.contact_email is not None


@dataclass(frozen=True)
class SourceView:
    id: str
    name: str
    enabled: bool
    has_key: bool | None  # None: the source takes no key
    key_hint: str | None


@dataclass(frozen=True)
class SourcesView:
    contact_email: str | None
    sources: list[SourceView]


def _settings(row: PaperSources | None) -> SourceSettings:
    if row is None:
        return SourceSettings()
    return SourceSettings(
        contact_email=row.contact_email,
        enabled={source: getattr(row, f"{source}_enabled") for source in SOURCES},
        api_keys={source: getattr(row, f"{source}_api_key") for source in KEYED},
    )


async def get(session: AsyncSession) -> SourceSettings:
    # populate_existing: after an upsert the identity map may still hold the row as it was loaded.
    return _settings(await session.get(PaperSources, True, populate_existing=True))


def view(sources: SourceSettings) -> SourcesView:
    return SourcesView(
        contact_email=sources.contact_email,
        sources=[
            SourceView(
                id=source,
                name=NAMES[source],
                enabled=sources.enabled[source],
                has_key=sources.api_keys[source] is not None if source in KEYED else None,
                key_hint=key_hint(sources.api_keys.get(source)),
            )
            for source in SOURCES
        ],
    )


async def seed_from_env(session: AsyncSession, mailto: str, s2_api_key: str) -> bool:
    """Creates the row from .env, only while there is none, so an OPENALEX_MAILTO that already turned OpenAlex on
    keeps it on. Returns whether it seeded."""
    email = mailto.strip() or None
    seeded = await session.scalar(
        insert(PaperSources)
        .values(
            id=True,
            contact_email=email,
            openalex_enabled=email is not None,
            semantic_scholar_api_key=s2_api_key.strip() or None,
        )
        .on_conflict_do_nothing(index_elements=["id"])
        .returning(PaperSources.id)
    )
    await session.commit()
    if seeded:
        logger.info("created the paper sources settings from .env, with OpenAlex %s", "on" if email else "off")
    return bool(seeded)


def _check_email(email: str | None) -> str | None:
    if email is None:
        return None
    email = email.strip()
    if len(email) > MAX_EMAIL or not _EMAIL.match(email):
        raise InvalidInput(BAD_EMAIL)
    return email


def _check_key(api_key: str | None) -> str | None:
    """The key without surrounding whitespace. The message never includes it."""
    if api_key is None:
        return None
    if not api_key.strip():
        raise InvalidInput(EMPTY_KEY)
    return api_key.strip()


async def update(session: AsyncSession, changes: Mapping[str, Any]) -> SourceSettings:
    """`changes` holds only what the request sent: `contact_email` (None removes it), `enabled` ({source: bool}) and
    `api_keys` ({source: key, or None to remove it}). Everything else keeps its value. Checked whole before saving."""
    values: dict[str, Any] = {}
    if "contact_email" in changes:
        values["contact_email"] = _check_email(changes["contact_email"])
    for source, on in (changes.get("enabled") or {}).items():
        if source not in SOURCES:
            raise InvalidInput(f"unknown paper source: {source}")
        values[f"{source}_enabled"] = on
    for source, api_key in (changes.get("api_keys") or {}).items():
        if source not in KEYED:
            raise InvalidInput(f"{source} doesn't take an API key")
        values[f"{source}_api_key"] = _check_key(api_key)
    if values:
        await session.execute(
            insert(PaperSources)
            .values(id=True, **values)
            .on_conflict_do_update(index_elements=["id"], set_={**values, "updated_at": func.now()})
        )
        await session.commit()
    return await get(session)
