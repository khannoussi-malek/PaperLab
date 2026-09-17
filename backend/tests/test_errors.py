"""Domain errors carry optional details a caller can act on (M6, D93)."""

import pytest

from app.core.errors import Conflict, DomainError, InvalidInput, NotFound


def test_details_round_trip():
    error = NotFound("unknown_workspace", available=["Alpha", "Thesis"])

    assert (str(error), error.details) == ("unknown_workspace", {"available": ["Alpha", "Thesis"]})


@pytest.mark.parametrize("kind", [NotFound, InvalidInput, Conflict])
def test_existing_raises_are_unchanged(kind):
    with pytest.raises(kind, match=r"^paper 42 not found$") as raised:
        raise kind("paper 42 not found")

    assert isinstance(raised.value, DomainError)
    assert (raised.value.args, raised.value.details) == (("paper 42 not found",), {})
    assert str(kind()) == ""
