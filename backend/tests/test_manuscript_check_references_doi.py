import uuid
from types import MappingProxyType, SimpleNamespace

import httpx
import pytest
from conftest import FakeProvider
from test_manuscript_papers import setup

from app.core import manuscripts
from app.core.errors import InvalidInput, NotFound
from app.core.manuscript_checks import doi_service
from app.core.manuscript_checks.references_doi import DoiEntry, check_dois, doi_entries
from app.providers import crossref

BIB = ("@article{a, doi={https://doi.org/10.1000/ABC}, title={T}}\n"
       "@article{b, doi={10.1000/abc}, title={T2}}\n@article{c, title={no doi}}\n@article{d, doi={10.1000/gone}}\n")


def test_entries_are_normalised_and_entries_without_a_doi_skipped():
    got = doi_entries(MappingProxyType({"r.bib": BIB, "paperlab.bib": "@misc{z, doi={10.9/z}}"}))
    assert [(e.key, e.doi, e.file, e.line) for e in got] == [
        ("a", "10.1000/abc", "r.bib", 1), ("b", "10.1000/abc", "r.bib", 2), ("d", "10.1000/gone", "r.bib", 4)]


def lookup_with(known, calls=None, boom=()):
    async def lookup(doi):
        (calls if calls is not None else []).append(doi)
        if doi in boom:
            raise httpx.ConnectError("down")
        return {"DOI": doi} if doi in known else None
    return lookup


E = [DoiEntry("a", "10.1/x", "r.bib", 1), DoiEntry("b", "10.1/x", "r.bib", 5), DoiEntry("c", "10.1/gone", "r.bib", 9)]


@pytest.mark.anyio
async def test_missing_doi_is_an_error_and_the_same_doi_is_asked_once():
    calls = []
    res = await check_dois(E, lookup_with({"10.1/x"}, calls))
    assert calls == ["10.1/x", "10.1/gone"]
    assert (res.checked, res.not_checked) == (2, 0)
    [f] = res.findings
    assert (f.check, f.severity, f.file, f.line) == ("references.doi_resolves", "error", "r.bib", 9)
    assert f.message == "DOI 10.1/gone (entry c) was not found at Crossref."
    assert f.fix_hint == ("Check the DOI for typos, or replace the entry with one from your library. "
                          "A made-up reference often shows up this way.")


@pytest.mark.anyio
async def test_a_failed_lookup_is_a_warning_and_counts_as_not_checked():
    res = await check_dois(E[:1], lookup_with(set(), boom={"10.1/x"}))
    [f] = res.findings
    assert (f.severity, f.message) == ("warning", "Could not check DOI 10.1/x (entry a): Crossref did not answer.")
    assert f.fix_hint == "Try again later."
    assert (res.checked, res.not_checked) == (0, 1)


@pytest.mark.anyio
async def test_the_cap_and_the_deadline_leave_the_rest_unchecked():
    res = await check_dois(E, lookup_with({"10.1/x", "10.1/gone"}), max_dois=1)
    assert (res.checked, res.not_checked, res.findings) == (1, 1, [])
    late = await check_dois(E, lookup_with({"10.1/x"}), deadline=0.0, clock=lambda: 1.0)
    assert (late.checked, late.not_checked, late.findings) == (0, 2, [])


@pytest.mark.anyio
async def test_no_dois_means_no_lookup():
    res = await check_dois([], lookup_with(set()))
    assert (res.checked, res.not_checked, res.findings) == (0, 0, [])


@pytest.fixture
def crossref_fake():
    return FakeProvider()


def wire(monkeypatch, fake, enabled=True, email=None):
    # the service passes email=None; the client is built exactly as production builds it, on a mock transport
    monkeypatch.setattr(doi_service, "new_client",
                        lambda email: crossref.new_client(email=email, transport=fake.transport))

    async def get(_session):
        return SimpleNamespace(enabled={"crossref": enabled}, contact_email=email)
    monkeypatch.setattr(doi_service.paper_sources, "get", get)


@pytest.mark.anyio
@pytest.mark.xdist_group("manuscript_rows")
async def test_service_sends_only_dois_and_reports(session, monkeypatch, crossref_fake):
    _, _, m = await setup(session, "Deep learning")
    await manuscripts.upsert_text(session, m.id, "refs.bib", BIB)
    crossref_fake.reply("/works/10.1000/abc", 200, json={"message": {"DOI": "10.1000/abc"}})
    crossref_fake.reply("/works/10.1000/gone", 404)
    wire(monkeypatch, crossref_fake)
    res = await doi_service.run_doi_check(session, m.id)
    assert (res.checked, [f.message for f in res.findings]) == (
        2, ["DOI 10.1000/gone (entry d) was not found at Crossref."])
    for r in crossref_fake.requests:
        assert r.url.path.startswith("/works/") and not r.url.params and r.content == b""


@pytest.mark.anyio
@pytest.mark.xdist_group("manuscript_rows")
async def test_a_set_contact_email_is_still_not_sent(session, monkeypatch, crossref_fake):
    _, _, m = await setup(session, "Deep learning")
    await manuscripts.upsert_text(session, m.id, "refs.bib", "@article{a, doi={10.1000/abc}}\n")
    crossref_fake.reply("/works/10.1000/abc", 200, json={"message": {"DOI": "10.1000/abc"}})
    wire(monkeypatch, crossref_fake, email="me@x.org")
    await doi_service.run_doi_check(session, m.id)
    [req] = crossref_fake.requests
    assert not req.url.params and "me@x.org" not in str(req.url) and req.content == b""


@pytest.mark.anyio
@pytest.mark.xdist_group("manuscript_rows")
async def test_service_refuses_when_crossref_is_off_and_sends_nothing(session, monkeypatch, crossref_fake):
    _, _, m = await setup(session, "Deep learning")
    await manuscripts.upsert_text(session, m.id, "refs.bib", BIB)
    wire(monkeypatch, crossref_fake, enabled=False)
    with pytest.raises(InvalidInput, match="crossref_disabled"):
        await doi_service.run_doi_check(session, m.id)
    assert crossref_fake.requests == []


@pytest.mark.anyio
@pytest.mark.xdist_group("manuscript_rows")
async def test_unknown_manuscript(session, monkeypatch, crossref_fake):
    wire(monkeypatch, crossref_fake)
    with pytest.raises(NotFound):
        await doi_service.run_doi_check(session, uuid.uuid4())


def test_latex_escapes_in_a_doi_are_removed_before_the_lookup():
    # Mendeley writes {\_} and other tools \_: both are the plain DOI, not a made-up one (a false error before)
    bib = ("@incollection{a, doi={10.1007/978-3-030-58452-8{\\_}13}}\n"
           "@article{b, doi={10.1000/abc\\_def}}\n@article{c, doi={10.1000/{abc}}}\n")
    got = doi_entries(MappingProxyType({"r.bib": bib}))
    assert [e.doi for e in got] == ["10.1007/978-3-030-58452-8_13", "10.1000/abc_def", "10.1000/abc"]


def test_a_doi_with_dot_segments_is_not_sent_to_crossref():
    # httpx would turn /works/10.1000/../../members into /members: such a DOI is never checked
    got = doi_entries(MappingProxyType({"r.bib": "@article{a, doi={10.1000/../../members}}\n"}))
    assert got == []


@pytest.mark.anyio
@pytest.mark.xdist_group("manuscript_rows")
async def test_no_transaction_is_open_while_crossref_is_asked(session, monkeypatch, crossref_fake):
    # The reads autobegin a transaction; holding it through a 60 s Crossref loop sits "idle in transaction"
    _, _, m = await setup(session, "Deep learning")
    await manuscripts.upsert_text(session, m.id, "refs.bib", "@article{a, doi={10.1000/abc}}\n")
    crossref_fake.reply("/works/10.1000/abc", 200, json={"message": {"DOI": "10.1000/abc"}})
    wire(monkeypatch, crossref_fake)
    real, seen = doi_service.new_client, []

    def spy(email):
        seen.append(session.in_transaction())
        return real(email)
    monkeypatch.setattr(doi_service, "new_client", spy)
    res = await doi_service.run_doi_check(session, m.id)
    assert seen == [False] and res.checked == 1
