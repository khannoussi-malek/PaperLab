import re
from pathlib import Path

from app.core.manuscript_checks.registry import REGISTRY

TESTS = Path(__file__).parent
NAME = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")


def test_registry_is_not_empty_and_names_are_unique():
    names = [c.name for c in REGISTRY]
    assert names and len(names) == len(set(names))


def test_every_check_is_well_formed():
    for c in REGISTRY:
        assert NAME.match(c.name), c.name
        assert c.cost in ("cheap", "full") and c.description.strip(), c.name


def test_every_check_family_has_its_self_check_file():
    for family in {c.name.split(".")[0] for c in REGISTRY}:
        assert (TESTS / f"test_manuscript_check_{family}.py").exists(), f"no self-check for family {family}"
