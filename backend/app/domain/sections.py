"""A paper section's role, where that role came from, and the reading lenses."""

from typing import Literal

Role = Literal[
    "abstract", "intro", "related", "method", "results", "discussion", "limitations", "conclusion", "back", "other"
]
Source = Literal["user", "keyword", "inherited", "position", "none"]
LensId = Literal["full", "key_ideas", "critical", "method", "related"]
