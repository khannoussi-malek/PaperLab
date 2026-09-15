"""The chart spec: what a saved chart stores. It names dataset, column and row ids, never numbers, so a chart shows the
current data every time it is drawn.

`type` picks the shape. A new chart type is a new member of `ChartSpec` plus one branch in the frontend's compiler;
a new optional field needs no version change. Limits matter most once a model writes specs (charts in chat).
"""

import math
import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator

SPEC_VERSION = 1
MAX_SERIES = 20
# Colours the categorical palette can keep apart for colour-blind readers (validated with the dataviz skill's checker
# on PaperLab's light and dark surfaces): 6 when neighbouring marks are compared (bars, lines, boxes), 3 when every pair
# is (scatter). More series than that go into small multiples, one series per panel.
MAX_COLORS = 6
MAX_SCATTER_COLORS = 3
MAX_DIMENSIONS = 30
MAX_ROW_FILTER = 5_000

HexColor = Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")]
# symlog: a log scale that keeps zero and negative values (Plotly has no such axis; the frontend transforms the data).
Scale = Literal["linear", "log", "symlog", "category"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Axis(_Strict):
    label: str = Field(default="", max_length=200)
    scale: Scale = "linear"


class Axes(_Strict):
    x: Axis = Field(default_factory=Axis)
    y: Axis = Field(default_factory=Axis)
    z: Axis = Field(default_factory=Axis)


class Layout(_Strict):
    barmode: Literal["group", "stack"] = "group"
    # "series": small multiples, one panel per series.
    facet: Literal["none", "series"] = "none"
    facet_columns: int = Field(default=2, ge=1, le=6)


class Series(_Strict):
    """One series: a y column (and x, z, error columns) from one dataset, optionally only some of its rows."""

    id: str = Field(min_length=1, max_length=40)
    name: str = Field(default="", max_length=200)
    dataset_id: uuid.UUID
    x: uuid.UUID | None = None
    y: uuid.UUID
    z: uuid.UUID | None = None
    # "cells": the ± error parsed from each y cell; a column id: that column's values.
    error: Literal["none", "cells"] | uuid.UUID = "none"
    rows: list[uuid.UUID] | None = Field(default=None, max_length=MAX_ROW_FILTER)  # None: every row
    trend: Literal["none", "linear"] = "none"
    # Reconciles units (0.91 vs 91%); the legend shows it, so a conversion is never hidden.
    multiply: float = 1.0
    color: HexColor | None = None

    @field_validator("multiply")
    @classmethod
    def usable_factor(cls, value: float) -> float:
        if not math.isfinite(value) or value == 0:
            raise ValueError("multiply must be a finite, non-zero number")
        return value


class _Chart(_Strict):
    version: Literal[1] = SPEC_VERSION
    axes: Axes = Field(default_factory=Axes)
    layout: Layout = Field(default_factory=Layout)


class SeriesChart(_Chart):
    type: Literal["bar", "line", "scatter", "box", "scatter3d"]
    series: list[Series] = Field(min_length=1, max_length=MAX_SERIES)

    @model_validator(mode="after")
    def drawable(self):
        if len({s.id for s in self.series}) != len(self.series):
            raise ValueError("series ids must be unique")
        for s in self.series:
            if self.type == "scatter3d" and (s.x is None or s.z is None):
                raise ValueError("a 3D scatter series needs x, y and z columns")
            if self.type != "scatter3d" and s.z is not None:
                raise ValueError("only a 3D scatter series has a z column")
            if s.trend != "none" and self.type not in ("line", "scatter"):
                raise ValueError("a trend line needs a line or scatter chart")
        if self.type == "scatter3d" and self.layout.facet != "none":
            raise ValueError("a 3D chart can't be split into small multiples")
        colors = MAX_SCATTER_COLORS if self.type in ("scatter", "scatter3d") else MAX_COLORS
        if self.layout.facet == "none" and len(self.series) > colors:
            raise ValueError(f"more than {colors} series in one panel can't be told apart; use small multiples")
        return self


class HeatmapChart(_Chart):
    type: Literal["heatmap"]
    dataset_id: uuid.UUID
    row_labels: uuid.UUID
    columns: list[uuid.UUID] = Field(min_length=1, max_length=MAX_DIMENSIONS)


class SurfaceChart(_Chart):
    """Surface or contour from long-format data: one row per (x, y) point, pivoted into a grid when drawn."""

    type: Literal["surface", "contour"]
    dataset_id: uuid.UUID
    x: uuid.UUID
    y: uuid.UUID
    z: uuid.UUID


class ParcoordsChart(_Chart):
    type: Literal["parcoords"]
    dataset_id: uuid.UUID
    dimensions: list[uuid.UUID] = Field(min_length=2, max_length=MAX_DIMENSIONS)
    color_by: uuid.UUID | None = None


ChartSpec = Annotated[SeriesChart | HeatmapChart | SurfaceChart | ParcoordsChart, Field(discriminator="type")]
ChartSpecAdapter: TypeAdapter[ChartSpec] = TypeAdapter(ChartSpec)

References = dict[uuid.UUID, tuple[set[uuid.UUID], set[uuid.UUID]]]


def references(spec: ChartSpec) -> References:
    """Per dataset id: the column ids and row ids the spec names."""
    refs: References = {}

    def add(dataset_id: uuid.UUID, columns=(), rows=()) -> None:
        named_columns, named_rows = refs.setdefault(dataset_id, (set(), set()))
        named_columns.update(c for c in columns if c is not None)
        named_rows.update(rows)

    if isinstance(spec, SeriesChart):
        for s in spec.series:
            error = s.error if isinstance(s.error, uuid.UUID) else None
            add(s.dataset_id, (s.x, s.y, s.z, error), s.rows or ())
    elif isinstance(spec, HeatmapChart):
        add(spec.dataset_id, (spec.row_labels, *spec.columns))
    elif isinstance(spec, SurfaceChart):
        add(spec.dataset_id, (spec.x, spec.y, spec.z))
    else:
        add(spec.dataset_id, (*spec.dimensions, spec.color_by))
    return refs
