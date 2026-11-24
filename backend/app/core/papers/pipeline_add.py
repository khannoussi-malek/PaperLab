"""The MCP tools that add papers: by DOI, arXiv ID or link, several at once, or an uploaded PDF."""

import logging
import uuid
from dataclasses import dataclass, field, replace
from pathlib import PurePosixPath
from typing import Literal
from urllib.parse import unquote, urlsplit

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.papers import enrichment, papers, pdf_links, pdf_recheck
from app.core.papers.pipeline import workspace_id
from app.core.platform import queue
from app.core.search import discovery
from app.core.workspaces import workspaces
from app.domain.errors import Conflict, DomainError, InvalidInput, NotFound, error_code
from app.models import Paper, PaperStatus


@dataclass(frozen=True)
class AddPaperResult:
    status: Literal["queued", "ingested", "already_in_library", "no_free_pdf", "saved_without_pdf"]
    paper_id: uuid.UUID | None = None
    landing_url: str | None = None
    title: str | None = None
    # no_free_pdf, or a queued link that fell back to its DOI: what each PDF URL tried said ({"url", "outcome"}).
    # no_free_pdf and saved_without_pdf: repository pages that may hold a copy.
    tried: list[dict[str, str]] = field(default_factory=list)
    free_copies: list[str] = field(default_factory=list)
    note: str | None = None  # something Claude should know about what happened, in words
    # The entries of `tried` that say a source couldn't answer now, not that it has no copy.
    temporary_failures: list[dict[str, str]] = field(default_factory=list)
    retry_scheduled: bool = False  # a saved paper is looked at again soon, with no need to add it again


NO_COPY_NOTE = "The paper is saved without a PDF; no free copy was found."
RETRY_NOTE = (
    "A source was busy or unreachable, which says nothing about whether a free copy exists. The paper is saved without "
    "a PDF and will be tried again automatically; no need to add it again."
)
NO_RETRY_NOTE = (
    "A source was busy or unreachable, which says nothing about whether a free copy exists. Automatic retries are off "
    "or used up; recheck_free_copies looks again."
)
NOT_SAVED_NOTE = (
    "A source was busy or unreachable, which says nothing about whether a free copy exists. Nothing was saved: add it "
    "again later, or pass save_without_pdf=True to have it retried automatically."
)


async def _attach(session: AsyncSession, paper: Paper, data: bytes, how: str) -> str | None:
    """attach_pdf for a paper saved without a PDF: None once attached (the caller queues ingest). When another
    request's PDF got there first (already_has_pdf), the re-read paper's answer instead, that request having queued
    its own ingest: "queued" while it ingests, else already_in_library."""
    try:
        await papers.attach_pdf(session, paper.id, data, how)
        return None
    except Conflict as exc:
        if str(exc) != "already_has_pdf":
            raise
    await session.refresh(paper)
    return "already_in_library" if paper.status in (PaperStatus.READY, PaperStatus.FAILED) else "queued"


DOI_ARXIV_HOSTS = ("doi.org", "dx.doi.org", "arxiv.org", "www.arxiv.org")


def _host(url: str) -> str:
    try:
        return urlsplit(url).hostname or ""
    except ValueError:  # malformed: check_url refuses it as unsafe_url
        return ""


def _identifier(identifier: str) -> tuple[str, str]:
    """("doi" | "arxiv" | "link", value). A title or an OpenAlex ID is refused (D217)."""
    text = identifier.strip().removeprefix("doi:").removeprefix("DOI:").strip()
    if "://" in text and _host(text) not in DOI_ARXIV_HOSTS:
        return "link", text  # a publisher PDF link can carry a DOI in its path
    kind, value = discovery.classify_query(text)
    if kind in ("doi", "arxiv"):
        return kind, value
    if "://" in text:  # a title with a colon parses as a URL scheme, so only "://" marks a link
        return "link", text
    raise InvalidInput("invalid_identifier", hint="Use a DOI, an arXiv ID or a direct PDF link.")


def _landing_url(kind: str, value: str) -> str:
    return f"https://doi.org/{value}" if kind == "doi" else f"https://arxiv.org/abs/{value}"


async def _queued(session: AsyncSession, paper, workspace_uuid: uuid.UUID | None) -> AddPaperResult:
    if workspace_uuid is not None:
        await workspaces.add_paper(session, workspace_uuid, paper.id)
    await queue.enqueue("ingest_paper", str(paper.id))
    return AddPaperResult(status="queued", paper_id=paper.id, title=paper.title)


async def _saved_without_pdf(session, paper, workspace_uuid, tried, copies) -> AddPaperResult:
    if workspace_uuid is not None:
        await workspaces.add_paper(session, workspace_uuid, paper.id)
    await papers.queue_biblio_fill(paper)
    if paper.abstract:
        try:
            await queue.enqueue("index_abstract", str(paper.id))
        except Exception:  # never stuck at `embedding`: ready without vectors, Settings' Try again embeds it
            await papers.set_status(session, paper.id, PaperStatus.READY)
            raise
    return AddPaperResult(
        status="saved_without_pdf", paper_id=paper.id, title=paper.title, tried=tried, free_copies=copies
    )


async def _add_found(
    session, providers, kind, value, workspace_uuid, tried_out=None, save_without_pdf=False
) -> AddPaperResult:
    found = await discovery.search(session, providers, value)
    match = next(
        (c for c in found.results if (c.doi or "").lower() == value or c.external_ids.get("arxiv") == value), None
    )
    if match is None and kind == "doi":  # Crossref's /works/{doi} answers an alias DOI with its canonical record
        match = next((c for c in found.results if "crossref" in c.sources), None)
    if match is None:
        raise NotFound("no_matching_paper", identifier=value)
    if match.paper_id is not None:
        try:
            return await _in_library(session, match.paper_id, workspace_uuid, providers)
        except Conflict as exc:  # find_pdf: this PDF-less paper's arXiv copy is held, which answers for it
            if str(exc) != discovery.ALREADY_IN_LIBRARY or "paper_id" not in exc.details:
                raise
            held = await _in_library(session, exc.details["paper_id"], workspace_uuid)
            return replace(held, tried=exc.details.get("tried", []))
    try:
        copies: list[str] = []
        tried_out = [] if tried_out is None else tried_out
        paper = await discovery.add(session, providers, match, settings.pdf_dir, tried_out, save_without_pdf, copies)
    except Conflict as exc:
        if str(exc) == discovery.ALREADY_IN_LIBRARY and "paper_id" in exc.details:  # its arXiv copy is held
            held = await _in_library(session, exc.details["paper_id"], workspace_uuid)  # no second search
            return replace(held, tried=exc.details.get("tried", []))
        if str(exc) != discovery.NO_FREE_PDF:
            raise
        return AddPaperResult(
            status="no_free_pdf",
            landing_url=_landing_url(kind, value),
            title=match.title,
            tried=exc.details.get("tried", []),
            free_copies=exc.details.get("free_copies", []),
        )
    if not paper.has_pdf:
        return await _saved_without_pdf(session, paper, workspace_uuid, tried_out, copies)
    return await _queued(session, paper, workspace_uuid)


async def _in_library(session, paper_id, workspace_uuid, providers=None) -> AddPaperResult:
    """A paper the library holds. Saved without a PDF and `providers` given, a free copy is looked for and attached."""
    paper = await papers.get_paper(session, paper_id)
    if not paper.has_pdf and providers is not None:
        # Filed after the search answers: a held arXiv copy (Conflict) answers for it, and the workspace gets only that.
        found = await _attach_found(session, providers, paper)
        if workspace_uuid is not None:
            await workspaces.add_paper(session, workspace_uuid, paper.id)
        return found
    if workspace_uuid is not None:
        await workspaces.add_paper(session, workspace_uuid, paper.id)
    if paper.file_path and paper.status == PaperStatus.FAILED:  # a retry, as the app's reingest does
        await papers.set_status(session, paper.id, PaperStatus.UPLOADED)
        await queue.enqueue("ingest_paper", str(paper.id))
    if not paper.has_pdf:
        return AddPaperResult(status="already_in_library", paper_id=paper.id, title=paper.title)
    status = "ingested" if paper.status == PaperStatus.READY else "queued"
    return AddPaperResult(status=status, paper_id=paper.id, title=paper.title)


async def _attach_found(session, providers, paper) -> AddPaperResult:
    """find_pdf for a paper saved without one: found, it is attached and ingest queued; else already_in_library with
    what was tried. A held arXiv copy of the same work (Conflict already_in_library) is the caller's to answer."""
    data, tried, copies = await discovery.find_pdf(session, providers, discovery.candidate_of(paper))
    if data is None:
        return AddPaperResult(
            status="already_in_library", paper_id=paper.id, title=paper.title, tried=tried, free_copies=copies,
            note=NO_COPY_NOTE,
        )
    if raced := await _attach(session, paper, data, "imported"):
        return AddPaperResult(status=raced, paper_id=paper.id, title=paper.title)
    await queue.enqueue("ingest_paper", str(paper.id))
    return AddPaperResult(status="queued", paper_id=paper.id, title=paper.title)


def _link_dois(link: str) -> list[str]:
    """The DOIs a publisher link's path may hold, longest first: a MIT path goes on after the DOI's own suffix."""
    doi = enrichment.normalize_doi(unquote(urlsplit(link).path))
    if doi is None:
        return []
    return list(dict.fromkeys([doi, "/".join(doi.split("/")[:2])]))


async def _link_by_doi(session, providers, link, tried, workspace_uuid, save_without_pdf=False) -> AddPaperResult:
    """A link that gave no PDF: its DOI's other free copies (arXiv, a repository) are tried, else the link's answer."""
    for doi in _link_dois(link):
        downloaded: list[dict[str, str]] = []
        try:
            found = await _add_found(session, providers, "doi", doi, workspace_uuid, downloaded, save_without_pdf)
        except NotFound:
            continue
        except Conflict:  # every source busy or off: the link's own answer stands
            break
        return replace(found, tried=[*tried, *(found.tried or downloaded)])
    return AddPaperResult(status="no_free_pdf", landing_url=link, tried=tried)


async def _add_link(session, providers, link, workspace_uuid, save_without_pdf=False) -> AddPaperResult:
    await pdf_links.check_url(link)
    data, tried = await discovery.download_pdf(providers.pdf, [link])
    if data is None:
        if tried[0]["outcome"] == "unsafe_url":  # a redirect to a private address is refused, as the link itself is
            raise InvalidInput("unsafe_url", url=link)
        return await _link_by_doi(session, providers, link, tried, workspace_uuid, save_without_pdf)
    # Like an upload: extraction and enrichment find the metadata. A paper already in the library becomes a second
    # copy, exactly as uploading the same PDF twice does (enrichment drops a DOI another paper holds).
    name = PurePosixPath(urlsplit(link).path).name or "paper.pdf"
    paper = await papers.create_paper(session, name, data, settings.pdf_dir)
    return await _queued(session, paper, workspace_uuid)


logger = logging.getLogger(__name__)


async def _note_temporary_failures(session: AsyncSession, result: AddPaperResult) -> AddPaperResult:
    """Separates "a source was busy" from "no free copy" on an answer without a PDF, and queues the next look at a paper
    the library now holds."""
    failures = discovery.temporary_failures(result.tried)
    if not failures or result.status in ("queued", "ingested"):
        return result
    if result.status == "no_free_pdf" or result.paper_id is None:
        return replace(result, temporary_failures=failures, note=NOT_SAVED_NOTE)
    paper = await session.get(Paper, result.paper_id)
    if paper is not None and paper.has_pdf:  # a held arXiv copy answered: no PDF is missing
        return result
    try:
        scheduled = await pdf_recheck.schedule_retry(session, result.paper_id)
    except Exception:  # the paper is saved already: the weekly look still finds it
        logger.exception("couldn't queue a retry for paper %s", result.paper_id)
        scheduled = False
    return replace(
        result, temporary_failures=failures, retry_scheduled=scheduled, note=RETRY_NOTE if scheduled else NO_RETRY_NOTE
    )


async def _add(session, providers, kind, value, workspace_uuid, save_without_pdf=False) -> AddPaperResult:
    if kind == "link":
        result = await _add_link(session, providers, value, workspace_uuid, save_without_pdf)
    else:
        result = await _add_found(session, providers, kind, value, workspace_uuid, save_without_pdf=save_without_pdf)
    return await _note_temporary_failures(session, result)


async def add_paper(
    session: AsyncSession, identifier: str, workspace: str | None = None, save_without_pdf: bool = False
) -> AddPaperResult:
    """Adds a paper by DOI, arXiv ID or direct PDF link, free copies only (D68, D217), and queues its ingest. With
    `save_without_pdf`, a DOI or arXiv ID with no free copy is saved by its details instead (status
    saved_without_pdf; its abstract is indexed)."""
    kind, value = _identifier(identifier)
    workspace_uuid = await workspace_id(session, workspace) if workspace is not None else None  # before any download
    if workspace_uuid is not None:
        await workspaces.require_writable(session, workspace_uuid)
    async with discovery.open_providers(session) as providers:
        return await _add(session, providers, kind, value, workspace_uuid, save_without_pdf)


MAX_ADD_PAPERS = 50


@dataclass(frozen=True)
class AddPapersItem:
    identifier: str
    status: str | None = None
    paper_id: uuid.UUID | None = None
    error: str | None = None
    tried: list[dict] = field(default_factory=list)
    free_copies: list[str] = field(default_factory=list)
    note: str | None = None
    temporary_failures: list[dict] = field(default_factory=list)
    retry_scheduled: bool = False


def _distinct(identifiers: list[str]) -> list[tuple[str, tuple[str, str] | None, str | None]]:
    """(identifier, parsed, error) once per distinct paper, in order. An unparseable one is its own entry."""
    seen, out = set(), []
    for raw in identifiers:
        text = raw.strip()
        try:
            parsed, error = _identifier(text), None
        except InvalidInput as exc:
            parsed, error = None, error_code(exc)
        if (parsed or text) not in seen:
            seen.add(parsed or text)
            out.append((text, parsed, error))
    return out


async def add_papers(
    session: AsyncSession, identifiers: list[str], workspace: str | None = None, save_without_pdf: bool = False
) -> list[AddPapersItem]:
    """add_paper for up to MAX_ADD_PAPERS identifiers with one set of providers; each item keeps its own error."""
    if len(identifiers) > MAX_ADD_PAPERS:
        raise InvalidInput("too_many_identifiers", max=MAX_ADD_PAPERS)
    workspace_uuid = await workspace_id(session, workspace) if workspace is not None else None  # before any download
    if workspace_uuid is not None:
        await workspaces.require_writable(session, workspace_uuid)
    items = []
    async with discovery.open_providers(session) as providers:
        for text, parsed, error in _distinct(identifiers):
            if parsed is not None:
                try:
                    added = await _add(session, providers, *parsed, workspace_uuid, save_without_pdf)
                    items.append(
                        AddPapersItem(
                            text,
                            status=added.status,
                            paper_id=added.paper_id,
                            tried=added.tried or [],
                            free_copies=added.free_copies or [],
                            note=added.note,
                            temporary_failures=added.temporary_failures,
                            retry_scheduled=added.retry_scheduled,
                        )
                    )
                    continue
                except DomainError as exc:
                    error = error_code(exc)
                except Exception:  # one provider's surprise must not lose the items already added
                    logger.exception("add_papers failed on %s", text)
                    await session.rollback()  # a failed flush leaves the session unusable until then
                    error = "failed"
            items.append(AddPapersItem(text, error=error))
    return items
