import httpx
import pytest

from app.providers import arxiv, biorxiv, core_ac, crossref, doaj, iacr_eprint, openaire, openalex, unpaywall
from app.providers.http import retrying

PROVIDERS = [arxiv, biorxiv, core_ac, crossref, doaj, iacr_eprint, openaire, openalex, unpaywall]


def test_a_real_transport_retries_a_failed_connection_and_a_test_one_is_kept():
    real = retrying(None)
    assert isinstance(real, httpx.AsyncHTTPTransport) and real._pool._retries == 2
    given = httpx.MockTransport(lambda r: httpx.Response(200))
    assert retrying(given) is given


@pytest.mark.parametrize("provider", PROVIDERS, ids=lambda p: p.__name__.rsplit(".", 1)[-1])
def test_every_metadata_client_retries_a_failed_connection(provider):
    # Docker's DNS in the live worker fails a lookup now and then: one blip must not leave a paper without metadata.
    client = provider.new_client()
    assert client._transport._pool._retries == 2
