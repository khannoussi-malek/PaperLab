"""Types every manuscript check shares."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

Severity = Literal["error", "warning", "info"]
Cost = Literal["cheap", "full"]
SEVERITIES: tuple[str, ...] = ("error", "warning", "info")  # also the sort order


@dataclass(frozen=True)
class Finding:
    check: str  # the Check's name, e.g. "citations.missing_keys"
    severity: Severity
    file: str | None  # manuscript-relative path; None = not tied to a file
    line: int | None  # 1-based; None = not tied to a line
    message: str
    fix_hint: str | None = None  # text only; never applied by PaperLab


@dataclass(frozen=True)
class ManuscriptInfo:
    """What a check may read about the manuscript row. New fields are added with defaults."""

    id: str
    main_file: str
    compile_status: str  # as a reader sees it (manuscripts.read_state): a dead `running` reads as failed
    compiled_at: datetime | None
    compile_log: str | None
    pdf_path: Path | None  # manuscripts.pdf_path(id) when the file exists, else None
    updated_at: datetime | None = None  # the row's; compared with compiled_at to spot a stale PDF
    template: str = "custom"  # manuscripts.template; "custom" names no folder


@dataclass(frozen=True)
class CheckContext:
    files: Mapping[str, str]  # path -> text, newlines normalised, text files only, read-only mapping
    known_keys: frozenset[str]  # cite keys that resolve: library, pinned, generated and the user's own .bib
    manuscript: ManuscriptInfo


@dataclass(frozen=True)
class Check:
    name: str  # stable, "family.rule", lowercase
    cost: Cost  # cheap = string work, safe on every save; full = may read the PDF or be slower
    description: str  # one line, shown in GET /checks
    run: Callable[[CheckContext], list[Finding]]
