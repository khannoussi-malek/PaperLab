"""SyncTeX index and lookups (M27 v2): which PDF spot a source line lands on, and the reverse. No web framework."""

import gzip
import re

SP_PER_POINT = 65781.76
_RECORD = re.compile(r"^([hvxkg$\[(])(\d+),(\d+)(?:,-?\d+)?:(-?\d+),(-?\d+)")
_INPUT = re.compile(r"^Input:(\d+):(.*)$")


def _relative(path: str, root: str) -> str | None:
    prefix = root.rstrip("/") + "/"
    if not path.startswith(prefix):
        return None  # the Tectonic bundle's files (or an empty name)
    rel = path[len(prefix):]
    while rel.startswith("./"):
        rel = rel[2:]
    return rel or None


def index(data: bytes, root: str) -> dict:
    """{"inputs": [rel paths], "records": [[page, input_i, line, x, y], ...]}; x/y in points, from the top-left."""
    unit, x_off, y_off, page = 1.0, 0.0, 0.0, 0
    tags: dict[str, int] = {}  # SyncTeX tag -> position in `inputs`
    inputs: list[str] = []
    records: list[list] = []
    for raw in gzip.decompress(data).decode(errors="replace").splitlines():
        m = _INPUT.match(raw)
        if m:
            rel = _relative(m.group(2), root)
            if rel is not None:
                tags[m.group(1)] = len(inputs)
                inputs.append(rel)
        elif raw.startswith("Unit:"):
            unit = float(raw[5:])
        elif raw.startswith("X Offset:"):
            x_off = float(raw[9:])
        elif raw.startswith("Y Offset:"):
            y_off = float(raw[9:])
        elif raw.startswith("{") and raw[1:].isdigit():
            page = int(raw[1:])
        elif page and (m := _RECORD.match(raw)):
            i = tags.get(m.group(2))
            line = int(m.group(3))
            if i is not None and line > 0:
                x = (int(m.group(4)) + x_off) * unit / SP_PER_POINT
                y = (int(m.group(5)) + y_off) * unit / SP_PER_POINT
                records.append([page, i, line, round(x, 2), round(y, 2)])
    return {"inputs": inputs, "records": records}


def forward(idx: dict, file: str, line: int) -> dict | None:
    if file not in idx["inputs"]:
        return None
    i = idx["inputs"].index(file)
    mine = [r for r in idx["records"] if r[1] == i]
    at_or_after = [r for r in mine if r[2] >= line]
    if at_or_after:
        target = min(r[2] for r in at_or_after)
    elif mine:
        target = max(r[2] for r in mine)
    else:
        return None
    page, _, _, x, y = min((r for r in mine if r[2] == target), key=lambda r: (r[0], r[4]))
    return {"page": page, "x": x, "y": y}


def inverse(idx: dict, page: int, x: float, y: float) -> dict | None:
    on_page = [r for r in idx["records"] if r[0] == page]
    if not on_page:
        return None
    best = min(on_page, key=lambda r: (round(abs(r[4] - y) / 2), abs(r[3] - x)))
    return {"file": idx["inputs"][best[1]], "line": best[2]}
