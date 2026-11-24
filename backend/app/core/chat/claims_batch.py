"""Checking every cited claim of a text at once, each against the papers it cites."""

import uuid
from dataclasses import dataclass, field, replace

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.chat import claim_text, claims
from app.core.chat.claim_extract import cited_claims
from app.core.chat.claim_text import RefEntry
from app.core.chat.claims import ClaimCheck
from app.core.citations import citations
from app.domain.errors import DomainError, InvalidInput
from app.providers.base import LLMError, LLMUnavailable

MAX_CLAIMS = 30


@dataclass(frozen=True)
class ClaimItem:
    claim: str  # the sentence with its citation(s) removed
    citation: citations.Citation
    check: ClaimCheck | None = None
    error: str | None = None  # citation_not_found | paper_not_in_library | ambiguous_citation | …
    candidates: list[str] = field(default_factory=list)  # titles when ambiguous
    warning: str | None = None  # year_mismatch: matched a paper the library dates a year away
    library_year: int | None = None
    doi: str | None = None  # the reference list's DOI for the paper (not the DOI written in the sentence)


def _entry_for(entries: dict, citation: citations.Citation) -> tuple[list[RefEntry], RefEntry | None, bool]:
    """The reference entries for a citation's key, narrowed by the co-authors it names; the one left, if one; and
    whether the key had several entries (then library candidates must show the co-authors too)."""
    found = entries.get((citations.fold(citation.surname), citation.year), [])
    wanted = [citations.fold(c) for c in citation.coauthors]
    named = [e for e in found if all(any(s == w or s.endswith(" " + w) for s in e.surnames) for w in wanted)]
    narrowed = named or found  # narrowing narrows, it never empties
    return narrowed, (narrowed[0] if len(narrowed) == 1 else None), len(found) > 1


async def _match(
    session, citation: citations.Citation, doi: str | None, workspace_id, strict: bool = False
) -> citations.Match:
    """The note's reference list first: its DOI picks the one paper even when the library holds duplicates or the
    paper has no authors or year. Author–year when the list gives none or the DOI isn't in the library, but then
    never a paper whose own DOI differs from the list's."""
    if doi:
        by_doi = await citations.match(session, replace(citation, kind="doi", doi=doi), workspace_id)
        if len(by_doi.paper_ids) == 1:
            return by_doi
    return await citations.match(session, citation, workspace_id, only_doi=doi, strict_coauthors=strict)


@dataclass(frozen=True)
class _Located:
    paper_id: uuid.UUID  # the one library paper the citation names
    extra: dict  # a year_mismatch warning, when the years differ


async def _not_in_workspace(session: AsyncSession, cited, entry_doi: str | None, several: bool) -> ClaimItem | None:
    """When the workspace holds no match: the item for a paper the library holds elsewhere, else None."""
    claim, citation = cited.claim, cited.citation
    elsewhere = await _match(session, citation, entry_doi, None, several)
    if elsewhere.paper_ids:
        return ClaimItem(claim, citation, error="paper_not_in_workspace", doi=entry_doi, candidates=elsewhere.titles)
    if elsewhere.unnamed:  # held, but its author list may be truncated: not a "not in library" claim
        return ClaimItem(claim, citation, error="ambiguous_citation", candidates=elsewhere.unnamed)
    return None


async def _locate(session: AsyncSession, cited, entries: dict, workspace_id: uuid.UUID | None) -> ClaimItem | _Located:
    """The paper a cited claim names, or the item saying why it can't be checked."""
    claim, citation = cited.claim, cited.citation
    if cited.error:
        return ClaimItem(claim, citation, error=cited.error)
    narrowed, entry, several = _entry_for(entries, citation) if citation.kind == "author_year" else ([], None, False)
    if len(narrowed) > 1:
        # entries still share this key: the citation can't say which paper it means
        candidates = await citations.match(session, citation, workspace_id)
        return ClaimItem(claim, citation, error="ambiguous_citation", candidates=candidates.titles)
    entry_doi = entry.doi if entry else None
    found = await _match(session, citation, entry_doi, workspace_id, several)
    if found.unnamed:  # the library's author list may be truncated, so the co-author isn't claimed absent
        return ClaimItem(claim, citation, error="ambiguous_citation", candidates=found.unnamed)
    extra = {"warning": "year_mismatch", "library_year": found.library_year} if found.library_year else {}
    if not found.paper_ids and workspace_id is not None:
        if (item := await _not_in_workspace(session, cited, entry_doi, several)) is not None:
            return item
    if not found.paper_ids:
        if entry:
            return ClaimItem(claim, citation, error="paper_not_in_library", doi=entry_doi)
        return ClaimItem(claim, citation, error="citation_not_found")
    if len(found.paper_ids) > 1:
        return ClaimItem(claim, citation, error="ambiguous_citation", candidates=found.titles)
    if len(claim.split()) < 3:
        return ClaimItem(claim, citation, error="empty_claim", **extra)
    return _Located(found.paper_ids[0], extra)


async def _checked_item(session: AsyncSession, cited, located: _Located, llm, save: bool) -> ClaimItem:
    """The check's verdict; a check that fails is this item's error, and the batch goes on."""
    claim, citation = cited.claim, cited.citation
    target = claims.ClaimTarget(paper_id=located.paper_id)
    try:
        check = await claims.verify_claim(session, claim, target, llm=llm, save=save)
    except DomainError as exc:
        return ClaimItem(claim, citation, error=str(exc) or "check_failed", **located.extra)
    except (LLMError, LLMUnavailable):
        return ClaimItem(claim, citation, error="check_failed", **located.extra)
    return ClaimItem(claim, citation, check=check, **located.extra)


async def verify_claims(
    session: AsyncSession, text: str, *, workspace_id: uuid.UUID | None = None, llm=None, save: bool = False
) -> list[ClaimItem]:
    """Checks every cited claim in `text`, in order: one item per citation, its claim the sentence, list item or
    table row that carries it (markdown is read as markdown). Send the whole note: a reference list at the end is never
    checked, but its DOIs are used to find the cited papers. A
    sentence that only points to another note is `not_a_claim`, neither matched nor checked.
    A citation that matches no paper is `citation_not_found` when the reference list doesn't name it either,
    `paper_not_in_library` (with the list's `doi`) when the list names it, and `paper_not_in_workspace` when the
    library holds it outside `workspace_id`; several matches are `ambiguous_citation` with the titles; none is guessed.
    A check that fails for one claim (its error code, or `check_failed` when the
    model can't be reached) is that item's error and the rest still run. More than 30 cited claims
    raises InvalidInput("too_many_claims") before any model call. `workspace_id` limits matching to one
    workspace (the caller resolves a name with workspaces.by_name). A citation a year away from the only matching
    paper still matches, with warning year_mismatch and the library's year.
    """
    body, references = claim_text.split_references(text)
    entries = claim_text.reference_entries(references)
    pending = cited_claims(body)
    if len(pending) > MAX_CLAIMS:
        raise InvalidInput("too_many_claims", detail=f"{len(pending)} cited claims; the limit is {MAX_CLAIMS}.")
    items = []
    for cited in pending:
        located = await _locate(session, cited, entries, workspace_id)
        if isinstance(located, ClaimItem):
            items.append(located)
            continue
        llm = await claims._llm(session, llm)  # no default model fails the whole batch, once, before any check
        items.append(await _checked_item(session, cited, located, llm, save))
    return items
