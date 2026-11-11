"""P8: checks over blueprint.json, the manuscript's plan (S2P B10). Silent without the file; never edits text."""

from pydantic import ValidationError

from app.core import manuscript_blueprint as bp
from app.core.manuscript_checks import latex_hygiene
from app.core.manuscript_checks.base import Check, CheckContext, Finding

W = "blueprint.words"
N = "blueprint.notation"


def load(ctx: CheckContext) -> tuple[bp.BlueprintSpec | None, str | None]:
    """(spec, None) | (None, problem) | (None, None) when there is no file."""
    text = ctx.files.get(bp.PATH)
    if text is None:
        return None, None
    try:
        return bp.parse(text), None
    except ValueError as exc:
        e = exc.errors()[0] if isinstance(exc, ValidationError) else None
        return None, (f"{'.'.join(map(str, e['loc'])) or 'file'}: {e['msg']}" if e else "not valid JSON")


def _words(ctx: CheckContext) -> list[Finding]:
    spec, problem = load(ctx)
    if problem:
        return [Finding(W, "warning", bp.PATH, 1, f"blueprint.json is not valid: {problem}",
                        "Fix the file; the blueprint checks are off until it parses.")]
    if spec is None:
        return []
    found, seen = [], set()
    for s in bp.sections(ctx.files):
        seen.add(s.id)
        if not s.measurable:  # the body is in an \input file: no honest count, so no warning
            continue
        band = bp.band(spec, s.id, ctx.manuscript.template)
        if band is None:
            continue
        lo, hi = band
        if s.words < lo:
            found.append(Finding(W, "warning", s.path, s.line,
                                 f'Section "{s.title}" has {s.words} words; the target is {lo} to {hi}.',
                                 f"Add about {lo - s.words} more words, or lower the target in blueprint.json."))
        elif s.words > hi:
            found.append(Finding(W, "warning", s.path, s.line,
                                 f'Section "{s.title}" has {s.words} words; more than the target of {lo} to {hi}.',
                                 f"Cut about {s.words - hi} words, or raise the target in blueprint.json."))
    found += [Finding(W, "info", bp.PATH, 1, f'target_words names "{k}", but no section has that title.',
                      "Rename the key to match a section title, or remove it.")
              for k in spec.target_words if k not in seen]
    return found


def _greek(symbol: str) -> set[str]:
    # same SYMBOL list and function-like rule as the latex check
    return {name for name, _ in latex_hygiene.symbols(symbol)}


def _notation(ctx: CheckContext) -> list[Finding]:
    spec, _ = load(ctx)
    if spec is None or not spec.notation:
        return []
    listed = set().union(*(_greek(s.symbol) for s in spec.notation))
    first, inline = latex_hygiene.math_symbols(ctx)
    used = set(first) | inline
    # a display-only symbol is latex.notation_undefined's to report; here only what the text introduced
    # but the plan lacks
    unlisted = sorted(inline - listed)
    unused = sorted(listed - used)
    return [Finding(N, "info", bp.PATH, 1,
                    f"\\{n} is used in the manuscript but is not in the blueprint's notation list.",
                    "Add it to notation in blueprint.json.") for n in unlisted] + [
        Finding(N, "info", bp.PATH, 1,
                f"\\{n} is listed in the blueprint's notation but never used in the manuscript.",
                "Use it, or remove it from the list.") for n in unused]


CHECKS = [
    Check(W, "cheap", "Section word counts against the blueprint's targets (or the template's bands)", _words),
    Check(N, "cheap", "Greek notation in the blueprint that is unused, or used but not listed", _notation),
]
