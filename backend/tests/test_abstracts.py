import pytest

from app.core.abstracts import is_citation_only, usable_abstract

NAACL = (
    "Yining Lu, Dixuan Wang, Tianjian Li, Dongwei Jiang, Sanjeev Khudanpur, Meng Jiang, Daniel Khashabi. "
    "Proceedings of the 2025 Conference of the Nations of the Americas Chapter of the Association for "
    "Computational Linguistics: Human Language Technologies (Volume 1: Long Papers). 2025."
)


@pytest.mark.parametrize(
    "text",
    [
        NAACL,
        "Shijie Wu, Mark Dredze. Proceedings of the 2019 Conference on Empirical Methods in Language Processing.",
        "Journal of the Royal Institute of International Affairs, Volume 8, Issue 1, 1929",
    ],
)
def test_a_citation_is_not_an_abstract(text):
    assert is_citation_only(text) and usable_abstract(text) is None


@pytest.mark.parametrize(
    "text",
    [
        "We present a controlled study of how templates in requirements specifications inhibit creativity.",
        "Creativity matters in software engineering. This paper was presented at the Conference on Design in 2021.",
        # A real abstract that names a venue and a year is long, or reads as prose.
        "Results from the 2019 workshop show that fixation affects designers across the conference's 2021 replication.",
        "x" * 500 + " Proceedings of a Conference 2020.",
        # Opens like an author list, then says something.
        "Creative Coding, Pair Programming, Design Fixation. This journal article shows how they relate.",
    ],
)
def test_an_abstract_stays_an_abstract(text):
    assert not is_citation_only(text) and usable_abstract(text) == text.strip()


@pytest.mark.parametrize("text", [None, "", "   "])
def test_nothing_is_no_abstract_and_no_citation(text):
    assert not is_citation_only(text) and usable_abstract(text) is None
