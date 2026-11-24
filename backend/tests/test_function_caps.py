"""Function-level clean-code caps: length, parameters and nesting, for every function in app/.

Each exception set is keyed `path::qualname` and may only shrink: a test fails when a listed function is within its
cap again (or gone), so a fix also drops its entry.
"""

import ast
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
APP = BACKEND / "app"

MAX_FUNCTION_LINES = 50
MAX_PARAMS = 6  # self/cls not counted
MAX_NESTING = 4  # if/for/while/with/try/match levels inside one function; a nested def counts on its own

ROUTE_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "websocket", "api_route"}
BLOCKS = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith, ast.Try, ast.TryStar, ast.Match)
FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)

LONG: set[str] = {
    "app/api/chat_stream.py::stream_output",
    "app/core/chat/chat.py::prepare",
    "app/core/chat/claims.py::verify_claim",
    "app/core/chat/claims_batch.py::verify_claims",
    "app/core/chat/retrieval.py::retrieve",
    "app/core/citations/citations.py::find",
    "app/core/citations/reference_listing.py::library_listing",
    "app/core/citations/references.py::_upsert",
    "app/core/manuscripts/draft_review.py::review",
    "app/core/manuscripts/manuscript_checks/number_provenance.py::_file",
    "app/core/manuscripts/manuscript_draft_review.py::start",
    "app/core/manuscripts/manuscript_evidence.py::find",
    "app/core/manuscripts/manuscript_review.py::start",
    "app/core/manuscripts/manuscript_section_review.py::start",
    "app/core/notes/charts.py::resolve",
    "app/core/notes/evidence_cards.py::request_cards",
    "app/core/papers/enrichment.py::fill_biblio",
    "app/core/papers/library.py::search",
    "app/core/search/batch_fetch.py::_find_or_create_external_ref",
    "app/core/search/batch_fetch.py::_store_candidates_as_hits",
    "app/core/search/batch_fetch.py::search_batch",
    "app/core/search/hit_import.py::import_hits",
    "app/core/search/hit_import.py::upload_hit_pdf",
    "app/core/search/hit_provenance.py::provenance",
    "app/core/search/prisma_export.py::prisma_export",
    "app/core/search/search_hits.py::list_hits",
    "app/core/search/snowball_run.py::snowball",
    "app/core/workspaces/package_screening_import.py::rebuild",
    "app/core/workspaces/reading_bridge.py::reading_queue",
    "app/core/workspaces/workspace_package.py::_parts",
    "app/main.py::create_app",
    "app/providers/llm_fake.py::_replies",
    "app/scripts/tectonic_sandbox_check.py::main",
    "app/workers/ingest.py::ingest_paper",
    "app/workers/screening_suggest.py::suggest_screening",
    "app/workers/workspace_search.py::run_workspace_search",
}
WIDE: set[str] = {
    "app/core/chat/chat_answers.py::save_answer",
    "app/core/chat/claims.py::_write_output",
    "app/core/chat/claims.py::verify_claim",
    "app/core/chat/retrieval.py::retrieve",
    "app/core/citations/citations_import_apply.py::_isolated",
    "app/core/citations/citations_import_apply.py::_one",
    "app/core/citations/citations_import_apply.py::apply",
    "app/core/citations/citations_import_route.py::route",
    "app/core/citations/citations_import_run.py::start",
    "app/core/manuscripts/draft_review.py::_lenses",
    "app/core/manuscripts/manuscript_agent.py::edit_file",
    "app/core/manuscripts/manuscript_review.py::start",
    "app/core/manuscripts/manuscript_section_review.py::start",
    "app/core/notes/capture.py::add_number",
    "app/core/notes/checks.py::_retrieved",
    "app/core/notes/datasets.py::create_dataset",
    "app/core/papers/enrichment.py::fill_biblio",
    "app/core/papers/library.py::search",
    "app/core/papers/merges.py::merge",
    "app/core/papers/pipeline.py::create_saved_search",
    "app/core/papers/pipeline.py::verify_claim",
    "app/core/papers/pipeline_add.py::_add_found",
    "app/core/search/batch_fetch.py::_insert_hit",
    "app/core/search/batch_fetch.py::_store_candidates_as_hits",
    "app/core/search/branches.py::set_branch",
    "app/core/search/discovery.py::add",
    "app/core/search/hit_provenance.py::_roots",
    "app/core/search/saved_searches.py::create",
    "app/core/search/search_hits.py::list_hits",
    "app/core/search/snowball_run.py::_seed_entry",
    "app/core/search/snowball_run.py::_store_hop",
    "app/core/search/snowball_run.py::snowball",
    "app/core/workspaces/briefs.py::save_brief",
    "app/core/workspaces/package_import.py::_papers_into",
    "app/core/workspaces/package_screening_import.py::_place_hit",
    "app/core/workspaces/triage.py::decide",
    "app/scripts/backfill_biblio.py::run",
}
DEEP: set[str] = {
    "app/core/manuscripts/manuscript_checks/wording.py::_overclaim",
    "app/providers/llm.py::OpenAICompatibleLLM.stream",
    "app/providers/search_model.py::_fetch",
    "app/workers/evidence_cards.py::generate_evidence_cards",
    "app/workers/ingest.py::ingest_paper",
    "app/workers/screening_suggest.py::suggest_screening",
    "app/workers/workspace_search.py::run_workspace_search",
}


def functions():
    """(key, node) for every function and method in app/, key = path::Outer.inner."""
    for path in sorted(APP.rglob("*.py")):
        rel = path.relative_to(BACKEND)
        stack: list[tuple[ast.AST, str]] = [(ast.parse(path.read_text()), "")]
        while stack:
            node, prefix = stack.pop()
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (*FUNCTIONS, ast.ClassDef)):
                    name = f"{prefix}{child.name}"
                    if isinstance(child, FUNCTIONS):
                        yield f"{rel}::{name}", child
                    stack.append((child, f"{name}."))
                else:
                    stack.append((child, prefix))


def length(fn: ast.AST) -> int:
    first = min([fn.lineno, *(d.lineno for d in fn.decorator_list)])
    return fn.end_lineno - first + 1


def params(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    a = fn.args
    names = [*a.posonlyargs, *a.args, *a.kwonlyargs]
    return len(names) - (1 if names and names[0].arg in ("self", "cls") else 0)


def is_route(fn: ast.AST) -> bool:
    """A FastAPI handler: its parameters are the declared HTTP contract, so they don't count against MAX_PARAMS."""
    return any(
        isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr in ROUTE_METHODS
        for d in fn.decorator_list
    )


def nesting(node: ast.AST, depth: int = 0) -> int:
    """Deepest block level inside `node`, not looking into nested functions, classes or lambdas. An `elif` is the
    same level as its `if`."""
    deepest = depth
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (*FUNCTIONS, ast.ClassDef, ast.Lambda)):
            continue
        if isinstance(child, ast.If) and isinstance(node, ast.If) and node.orelse == [child]:
            deepest = max(deepest, nesting(child, depth))  # elif
        elif isinstance(child, BLOCKS):
            deepest = max(deepest, nesting(child, depth + 1))
        else:
            deepest = max(deepest, nesting(child, depth))
    return deepest


def over(measure, cap: int, skip=lambda fn: False) -> set[str]:
    return {key for key, fn in functions() if not skip(fn) and measure(fn) > cap}


def check(found: set[str], allowed: set[str], name: str, cap: int, what: str):
    assert sorted(found - allowed) == [], f"bring these to {cap} {what} or fewer"
    assert sorted(allowed - found) == [], f"drop these from {name}: within the cap now (or gone)"


def test_functions_stay_short():
    check(over(length, MAX_FUNCTION_LINES), LONG, "LONG", MAX_FUNCTION_LINES, "lines")


def test_functions_take_few_parameters():
    check(over(params, MAX_PARAMS, skip=is_route), WIDE, "WIDE", MAX_PARAMS, "parameters")


def test_functions_nest_shallowly():
    check(over(nesting, MAX_NESTING), DEEP, "DEEP", MAX_NESTING, "levels")


def test_nesting_counts_blocks_not_elif_or_nested_defs():
    fn = ast.parse(
        "def f(x):\n"
        "    if x:\n"
        "        for i in x:\n"
        "            pass\n"
        "    elif x is None:\n"
        "        with x:\n"
        "            try:\n"
        "                pass\n"
        "            except E:\n"
        "                pass\n"
        "    def g():\n"
        "        if a:\n"
        "            if b:\n"
        "                if c:\n"
        "                    pass\n"
    ).body[0]
    assert nesting(fn) == 3  # elif → with → try; g's three ifs count for g alone
    assert nesting(fn.body[-1]) == 3


def test_routes_are_told_apart_from_helpers():
    route, helper = ast.parse("@router.get('/x')\ndef a(): pass\n@cache\ndef b(): pass").body
    assert is_route(route) and not is_route(helper)
