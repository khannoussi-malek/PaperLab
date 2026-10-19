"""M77: the test run refuses the live database when this branch carries a migration it doesn't have yet."""

import asyncio

from db_guard import refusal
from sqlalchemy.engine import make_url

LINEAGE = ["0050", "0049", "0048"]  # the code's head first, then its ancestors


def test_a_branch_ahead_of_the_live_database_is_refused():
    message = refusal("paperlab", "0049", LINEAGE)
    assert message is not None
    assert "0050" in message and "TEST_DATABASE_URL" in message and "throwaway" in message


def test_an_unmigrated_live_database_is_refused_too():
    assert refusal("paperlab", None, LINEAGE) is not None


def test_matching_versions_run_as_today():
    assert refusal("paperlab", "0050", LINEAGE) is None


def test_a_throwaway_database_is_never_refused():
    assert refusal("paperlab_m50", "0049", LINEAGE) is None


def test_a_live_database_ahead_of_the_code_is_not_this_guards_business():
    assert refusal("paperlab", "0051", LINEAGE) is None  # another branch migrated it; main's tests may still run


def test_check_reads_the_real_version_and_refuses_when_the_code_is_ahead(monkeypatch, database_url):
    # The test database posing as the live one, and a code lineage one migration past it: today's near-miss.
    import db_guard

    current = asyncio.run(db_guard._db_version(database_url))
    monkeypatch.setattr(db_guard, "LIVE_DATABASE", make_url(database_url).database)
    monkeypatch.setattr(db_guard, "code_lineage", lambda: ["9999_next", current, "0001"])
    assert "9999_next" in (db_guard.check(database_url) or "")
    monkeypatch.setattr(db_guard, "code_lineage", lambda: [current, "0001"])
    assert db_guard.check(database_url) is None


def test_the_code_lineage_starts_at_the_alembic_head():
    import db_guard

    lineage = db_guard.code_lineage()
    assert lineage[-1] == "0001" and len(set(lineage)) == len(lineage)
