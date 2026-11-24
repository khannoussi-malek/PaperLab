"""Function-level clean-code caps: length, parameters and nesting, for every function in app/.

Each exception list maps `path::qualname` to the size recorded when it was listed. A listed function may not grow past
that size, and the lists may only shrink: a test fails when a listed function is within its cap again (or gone), so a
fix also drops its entry.
"""

import ast
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
APP = BACKEND / "app"

MAX_FUNCTION_LINES = 50
MAX_PARAMS = 6  # self/cls not counted; *args and **kwargs count one each
MAX_NESTING = 4  # if/for/while/with/try/match levels inside one function; a nested def counts on its own

ROUTE_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "websocket", "api_route"}
BLOCKS = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith, ast.Try, ast.TryStar, ast.Match)
FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)

LONG: dict[str, int] = {
    "app/api/chat_stream.py::stream_output": 53,
    "app/core/citations/citations.py::find": 51,
    "app/core/citations/reference_listing.py::library_listing": 52,
    "app/core/citations/references.py::_upsert": 55,
    "app/core/manuscripts/draft_review.py::review": 59,
    "app/core/manuscripts/manuscript_checks/number_provenance.py::_file": 51,
    "app/core/manuscripts/manuscript_draft_review.py::start": 51,
    "app/core/manuscripts/manuscript_evidence.py::find": 52,
    "app/core/manuscripts/manuscript_review.py::start": 52,
    "app/core/manuscripts/manuscript_section_review.py::start": 71,
    "app/core/notes/charts.py::resolve": 54,
    "app/core/notes/evidence_cards.py::request_cards": 65,
    "app/core/workspaces/package_screening_import.py::rebuild": 71,
    "app/core/workspaces/reading_bridge.py::reading_queue": 51,
    "app/core/workspaces/workspace_package.py::_parts": 51,
    "app/main.py::create_app": 67,
    "app/providers/llm_fake.py::_replies": 51,
    "app/scripts/tectonic_sandbox_check.py::main": 53,
    "app/workers/ingest.py::ingest_paper": 73,
    "app/workers/screening_suggest.py::suggest_screening": 98,
    "app/workers/workspace_search.py::run_workspace_search": 106,
}
WIDE: dict[str, int] = {
    "app/core/chat/chat_answers.py::save_answer": 8,
    # The search core: ten callers and nine test fakes pass these keyword options by name.
    "app/core/chat/retrieval.py::retrieve": 9,
    "app/core/citations/citations_import_apply.py::_isolated": 7,
    "app/core/citations/citations_import_apply.py::_one": 7,
    "app/core/citations/citations_import_apply.py::apply": 8,
    "app/core/citations/citations_import_route.py::route": 8,
    "app/core/citations/citations_import_run.py::start": 7,
    "app/core/manuscripts/draft_review.py::_lenses": 7,
    "app/core/manuscripts/manuscript_agent.py::edit_file": 7,
    "app/core/manuscripts/manuscript_review.py::start": 7,
    "app/core/manuscripts/manuscript_section_review.py::start": 7,
    "app/core/notes/capture.py::add_number": 8,
    "app/core/notes/checks.py::_retrieved": 7,
    "app/core/notes/datasets.py::create_dataset": 7,
    "app/core/workspaces/briefs.py::save_brief": 7,
    "app/core/workspaces/package_import.py::_papers_into": 7,
    "app/core/workspaces/package_screening_import.py::_place_hit": 7,
    "app/core/workspaces/triage.py::decide": 11,
    "app/scripts/backfill_biblio.py::run": 7,
}
DEEP: dict[str, int] = {
    "app/core/manuscripts/manuscript_checks/wording.py::_overclaim": 5,
    "app/providers/llm.py::OpenAICompatibleLLM.stream": 5,
    "app/providers/search_model.py::_fetch": 5,
    "app/workers/evidence_cards.py::generate_evidence_cards": 5,
    "app/workers/ingest.py::ingest_paper": 5,
    "app/workers/screening_suggest.py::suggest_screening": 5,
    "app/workers/workspace_search.py::run_workspace_search": 6,
}


def functions():
    """(key, node) for every function and method in app/, key = path::Outer.inner."""
    for path in sorted(APP.rglob("*.py")):
        rel = path.relative_to(BACKEND)
        stack: list[tuple[ast.AST, str]] = [(ast.parse(path.read_text(encoding="utf-8")), "")]
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
    star = (a.vararg is not None) + (a.kwarg is not None)
    return len(names) + star - (1 if names and names[0].arg in ("self", "cls") else 0)


def is_route(fn: ast.AST) -> bool:
    """A FastAPI handler: its parameters are the declared HTTP contract, so they don't count against MAX_PARAMS."""
    return any(
        isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr in ROUTE_METHODS
        for d in fn.decorator_list
    )


def nesting(node: ast.AST, depth: int = 0) -> int:
    """Deepest block level inside `node`, not looking into nested functions, classes or lambdas. An `elif` is the
    same level as its `if` (it starts in the `if`'s column; an `if` inside an `else:` is indented)."""
    deepest = depth
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (*FUNCTIONS, ast.ClassDef, ast.Lambda)):
            continue
        elif_ = isinstance(child, ast.If) and isinstance(node, ast.If) and node.orelse == [child]
        if elif_ and child.col_offset == node.col_offset:
            deepest = max(deepest, nesting(child, depth))  # elif
        elif isinstance(child, BLOCKS):
            deepest = max(deepest, nesting(child, depth + 1))
        else:
            deepest = max(deepest, nesting(child, depth))
    return deepest


def over(measure, cap: int, skip=lambda fn: False) -> dict[str, int]:
    sizes = {key: measure(fn) for key, fn in functions() if not skip(fn)}
    return {key: size for key, size in sizes.items() if size > cap}


def check(found: dict[str, int], allowed: dict[str, int], name: str, cap: int, what: str):
    assert sorted(found.keys() - allowed.keys()) == [], f"bring these to {cap} {what} or fewer"
    grown = sorted(f"{key}: {allowed[key]} -> {size}" for key, size in found.items() if size > allowed.get(key, size))
    assert grown == [], f"these listed functions grew; bring them back to their recorded {what} or below"
    assert sorted(allowed.keys() - found.keys()) == [], f"drop these from {name}: within the cap now (or gone)"


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
    else_if = ast.parse("def h(x):\n    if x:\n        pass\n    else:\n        if not x:\n            pass\n").body[0]
    assert nesting(else_if) == 2  # an if inside else: is a level deeper, unlike elif


def test_routes_are_told_apart_from_helpers():
    route, helper = ast.parse("@router.get('/x')\ndef a(): pass\n@cache\ndef b(): pass").body
    assert is_route(route) and not is_route(helper)
