import math
import uuid

import pytest
from pydantic import ValidationError

from app.core.chart_spec import MAX_DIMENSIONS, MAX_SERIES, ChartSpecAdapter, references

DATASET, OTHER = uuid.uuid4(), uuid.uuid4()
X, Y, Z, ERR = (uuid.uuid4() for _ in range(4))
ROW = uuid.uuid4()


def series(**fields) -> dict:
    return {"id": "s1", "dataset_id": str(DATASET), "y": str(Y), **fields}


def parse(spec: dict):
    return ChartSpecAdapter.validate_python(spec)


def test_a_bar_chart_gets_defaults_for_everything_it_leaves_out():
    spec = parse({"type": "bar", "series": [series(x=str(X))]})

    assert spec.model_dump(mode="json") == {
        "version": 1,
        "type": "bar",
        "axes": {"x": {"label": "", "scale": "linear"}, "y": {"label": "", "scale": "linear"},
                 "z": {"label": "", "scale": "linear"}},
        "layout": {"barmode": "group", "facet": "none", "facet_columns": 2},
        "series": [{"id": "s1", "name": "", "dataset_id": str(DATASET), "x": str(X), "y": str(Y), "z": None,
                    "error": "none", "rows": None, "trend": "none", "multiply": 1.0, "color": None}],
    }  # fmt: skip


def test_every_chart_type_parses_to_its_own_shape():
    parsed = [
        parse({"type": kind, "series": [series(x=str(X))]}) for kind in ("bar", "line", "scatter", "box")
    ] + [
        parse({"type": "scatter3d", "series": [series(x=str(X), z=str(Z))]}),
        parse({"type": "heatmap", "dataset_id": str(DATASET), "row_labels": str(X), "columns": [str(Y), str(Z)]}),
        parse({"type": "surface", "dataset_id": str(DATASET), "x": str(X), "y": str(Y), "z": str(Z)}),
        parse({"type": "contour", "dataset_id": str(DATASET), "x": str(X), "y": str(Y), "z": str(Z)}),
        parse({"type": "parcoords", "dataset_id": str(DATASET), "dimensions": [str(X), str(Y)], "color_by": None}),
    ]
    assert [type(spec).__name__ for spec in parsed] == [
        "SeriesChart", "SeriesChart", "SeriesChart", "SeriesChart", "SeriesChart",
        "HeatmapChart", "SurfaceChart", "SurfaceChart", "ParcoordsChart",
    ]  # fmt: skip


def test_an_error_is_none_from_the_cells_or_another_column():
    for error in ("none", "cells", str(ERR)):
        assert str(parse({"type": "scatter", "series": [series(error=error)]}).series[0].error) == error


@pytest.mark.parametrize(
    "spec",
    [
        {"type": "pie", "series": [series()]},
        {"type": "bar", "series": []},
        {"type": "bar", "series": [series(id=f"s{i}") for i in range(MAX_SERIES + 1)]},
        {"type": "bar", "series": [series(), series()]},  # two series with the same id
        {"type": "bar", "series": [series(z=str(Z))]},  # z only belongs to 3D
        {"type": "scatter3d", "series": [series(x=str(X))]},  # 3D needs x and z
        {"type": "bar", "series": [series(trend="linear")]},  # a trend line needs a line or scatter chart
        {"type": "bar", "series": [series(multiply=0)]},
        {"type": "bar", "series": [series(multiply=math.inf)]},
        {"type": "bar", "series": [series(color="red")]},
        {"type": "bar", "series": [series(error="sometimes")]},
        {"type": "bar", "series": [series()], "title": "titles live on the chart, not in its spec"},
        {"type": "bar", "version": 2, "series": [series()]},
        {"type": "bar", "series": [series()], "axes": {"y": {"scale": "exponential"}}},
        {"type": "heatmap", "dataset_id": str(DATASET), "row_labels": str(X), "columns": []},
        {"type": "parcoords", "dataset_id": str(DATASET), "dimensions": [str(X)]},
        {"type": "parcoords", "dataset_id": str(DATASET),
         "dimensions": [str(uuid.uuid4()) for _ in range(MAX_DIMENSIONS + 1)]},
        {"type": "surface", "dataset_id": str(DATASET), "x": str(X), "y": str(Y)},
    ],
)
def test_specs_that_cannot_be_drawn_are_refused(spec):
    with pytest.raises(ValidationError):
        parse(spec)


def test_references_name_every_dataset_column_and_row_a_spec_uses():
    spec = parse({"type": "line", "series": [
        series(x=str(X), error=str(ERR), rows=[str(ROW)]),
        {"id": "s2", "dataset_id": str(OTHER), "y": str(Z), "error": "cells"},
    ]})  # fmt: skip

    refs = references(spec)

    assert refs == {DATASET: ({X, Y, ERR}, {ROW}), OTHER: ({Z}, set())}
    heatmap = parse({"type": "heatmap", "dataset_id": str(DATASET), "row_labels": str(X), "columns": [str(Y)]})
    assert references(heatmap) == {DATASET: ({X, Y}, set())}
    parcoords = parse(
        {"type": "parcoords", "dataset_id": str(DATASET), "dimensions": [str(X), str(Y)], "color_by": str(Z)}
    )
    assert references(parcoords) == {DATASET: ({X, Y, Z}, set())}
