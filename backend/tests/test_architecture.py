"""The backend's layers: every import points down the table below, and no module grows past MAX_LINES.

The two exception lists may only shrink: a test fails when an entry is no longer needed.
"""

import ast
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
APP = BACKEND / "app"
MAX_LINES = 400

# Lowest first. A module may import its own package and any package of a lower rank, never a sibling of the
# same rank (schemas and providers don't know each other; api, workers and scripts don't either).
RANK = {
    "domain": 0,  # pure types, constants and rules: stdlib and pydantic only
    "config": 1,
    "db": 2,
    "models": 2,
    "schemas": 3,
    "providers": 3,
    "core": 4,
    "api": 5,
    "workers": 5,
    "scripts": 5,
    "main": 6,
}
SAME_RANK_OK = {("models", "db")}  # the ORM models sit on db's Base

# importer module -> imported module: reason. Kept on purpose; see docs in each importer.
ALLOWED_UPWARD: dict[tuple[str, str], str] = {
    # Source ids derive from the registry of fetchers; a copied list would drift.
    ("app.schemas.paper_sources", "app.core.search.source_registry"): "source ids",
    ("app.schemas.workspace_search", "app.core.search.source_registry"): "source ids",
    ("app.scripts.tectonic_sandbox_check", "app.workers.manuscripts"): "a check script for the worker's own sandbox",
}
# The fake model answers each feature by its system prompt, so it reads every prompt (lazily): a test double for
# the whole app, picked by LLM_PROVIDER=fake.
FAKE_MODEL_READS = (
    "chat.answer_check", "chat.chat", "chat.chat_charts", "chat.claim_detect", "chat.claims", "chat.each_paper",
    "manuscripts.diagram", "manuscripts.draft_review", "manuscripts.section_review", "notes.checks",
    "notes.evidence_cards", "notes.note_suggestions", "notes.number_suggest", "search.screening_suggest",
)
ALLOWED_UPWARD |= {("app.providers.llm_fake", f"app.core.{name}"): "fake model" for name in FAKE_MODEL_READS}

# Files allowed over MAX_LINES today (paths relative to backend/). Split one, then take it off.
OVER_MAX: set[str] = {
    "app/api/chat.py",
    "app/core/search/candidates.py",
    "app/core/chat/chat.py",
    "app/core/citations/citations_export.py",
    "app/core/citations/citations_import.py",
    "app/core/citations/citations_import_apply.py",
    "app/core/chat/claims.py",
    "app/core/search/discovery.py",
    "app/core/papers/enrichment.py",
    "app/core/notes/evidence_cards.py",
    "app/core/search/hit_links.py",
    "app/core/manuscripts/manuscript_checks/number_provenance.py",
    "app/core/notes/notes.py",
    "app/core/papers/pipeline.py",
    "app/core/citations/references.py",
    "app/core/search/screening.py",
    "app/core/platform/skills.py",
    "app/core/workspaces/workspace_package.py",
    "app/core/workspaces/workspace_package_screening.py",
    "app/core/search/workspace_search.py",
    "app/providers/discovery_fake.py",
    "app/schemas/workspace_search.py",
    "app/workers/ingest.py",
}


def module_name(path: Path) -> str:
    parts = path.relative_to(BACKEND).with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def is_module(dotted: str) -> bool:
    base = BACKEND.joinpath(*dotted.split("."))
    return base.with_suffix(".py").exists() or (base / "__init__.py").exists()


def is_type_checking(node: ast.If) -> bool:
    test = node.test
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
    )


def absolute(node: ast.ImportFrom, importer: str, is_package: bool) -> str | None:
    """The module an ImportFrom names, with `from . import x` / `from ..y import z` resolved against the importer."""
    if node.level == 0:
        return node.module
    base = importer.split(".")[: len(importer.split(".")) - node.level + (1 if is_package else 0)]
    return ".".join(base + ([node.module] if node.module else []))


def runtime_imports(tree: ast.AST, importer: str = "", is_package: bool = False):
    """Every app.* module imported at runtime (inside functions too), skipping `if TYPE_CHECKING:` blocks."""
    stack = [tree]
    while stack:
        node = stack.pop()
        if isinstance(node, ast.If) and is_type_checking(node):
            stack.extend(node.orelse)
            continue
        if isinstance(node, ast.Import):
            yield from (a.name for a in node.names if a.name.startswith("app."))
        elif isinstance(node, ast.ImportFrom) and (module := absolute(node, importer, is_package)):
            if module == "app" or module.startswith("app."):
                for alias in node.names:
                    sub = f"{module}.{alias.name}"
                    yield sub if is_module(sub) else module
        stack.extend(ast.iter_child_nodes(node))


def layer(module: str) -> str:
    return module.split(".")[1]


def sources():
    for path in sorted(APP.rglob("*.py")):
        yield path, path.read_text()


def layer_breaks() -> set[tuple[str, str]]:
    found = set()
    for path, text in sources():
        importer = module_name(path)
        if importer == "app":
            continue
        src = layer(importer)
        tree = ast.parse(text, feature_version=(3, 12))
        for imported in runtime_imports(tree, importer, path.name == "__init__.py"):
            if imported == "app":
                continue
            dst = layer(imported)
            if src == dst or (src, dst) in SAME_RANK_OK:
                continue
            if RANK[dst] >= RANK[src]:
                found.add((importer, imported))
    return found


def test_every_app_package_has_a_rank():
    packages = {p.name for p in APP.iterdir() if p.is_dir() and any(p.rglob("*.py"))}
    packages |= {p.stem for p in APP.glob("*.py") if p.stem != "__init__"}
    assert packages - RANK.keys() == set(), "add the new package to RANK in tests/test_architecture.py"


def test_relative_imports_resolve_against_the_importer():
    up = ast.parse("from ..workers import x").body[0]
    assert absolute(up, "app.api.chat", is_package=False) == "app.workers"
    here = ast.parse("from .base import Check").body[0]
    checks = "app.core.manuscripts.manuscript_checks"
    assert absolute(here, checks, is_package=True) == f"{checks}.base"


def test_imports_point_down():
    unexpected = sorted(layer_breaks() - ALLOWED_UPWARD.keys())
    assert unexpected == [], "imports that point up or sideways:\n" + "\n".join(f"  {a} -> {b}" for a, b in unexpected)


def test_allowed_exceptions_are_still_needed():
    assert sorted(ALLOWED_UPWARD.keys() - layer_breaks()) == [], "drop these from ALLOWED_UPWARD"


def test_no_module_over_max_lines():
    long = {str(p.relative_to(BACKEND)) for p, text in sources() if text.count("\n") > MAX_LINES}
    assert sorted(long - OVER_MAX) == [], f"split these below {MAX_LINES} lines"
    assert sorted(OVER_MAX - long) == [], "drop these from OVER_MAX: they are short enough now (or gone)"


def test_core_is_grouped_by_area():
    loose = sorted(p.name for p in (APP / "core").glob("*.py") if p.name != "__init__.py")
    assert loose == [], "put these in the area package they serve (app/core/<area>/)"
