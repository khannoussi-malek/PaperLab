//! What the reader typed or pasted: a DOI, an arXiv ID, a link, or words to match against the library.

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Input {
    Empty,
    Doi(String),
    Arxiv(String),
    Link(String),
    Text(String),
}

impl Input {
    /// The query sent to `/api/discovery/search`, or `None` for library text.
    pub fn lookup(&self) -> Option<&str> {
        match self {
            Input::Doi(q) | Input::Arxiv(q) | Input::Link(q) => Some(q),
            Input::Empty | Input::Text(_) => None,
        }
    }
}

const DOI_PREFIXES: [&str; 5] = ["https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "doi.org/", "doi:"];
const ARXIV_PREFIXES: [&str; 5] =
    ["https://arxiv.org/abs/", "http://arxiv.org/abs/", "https://arxiv.org/pdf/", "arxiv.org/abs/", "arxiv:"];

pub fn classify(raw: &str) -> Input {
    let s = raw.trim();
    if s.is_empty() {
        return Input::Empty;
    }
    let bare = strip_prefix_ci(s, &DOI_PREFIXES).unwrap_or(s);
    if let Some(doi) = doi(bare) {
        return Input::Doi(doi);
    }
    let bare = strip_prefix_ci(s, &ARXIV_PREFIXES).unwrap_or(s);
    let bare = bare.trim_start_matches(['(', '"', '\'']).trim_end_matches(['.', ',', ';', ')', '"', '\'']);
    let bare = bare.strip_suffix(".pdf").unwrap_or(bare);
    if arxiv_id(bare) {
        return Input::Arxiv(bare.to_owned());
    }
    if s.starts_with("https://") || s.starts_with("http://") {
        return Input::Link(s.to_owned());
    }
    Input::Text(s.to_owned())
}

/// Paper sites whose article links name a paper without a DOI in them (PaperLab reads the page for it): a host, and
/// the start of its article paths, so a site's other pages (news, search, a dictionary) don't count.
const PAPER_PAGES: [(&str, &str); 19] = [
    ("nature.com", "/articles/"),
    ("ieeexplore.ieee.org", "/document/"),
    ("sciencedirect.com", "/science/article/"),
    ("pubmed.ncbi.nlm.nih.gov", "/"),
    ("ncbi.nlm.nih.gov", "/pmc/articles/"),
    ("pmc.ncbi.nlm.nih.gov", "/articles/"),
    ("openreview.net", "/forum"),
    ("aclanthology.org", "/"),
    ("semanticscholar.org", "/paper/"),
    ("jstor.org", "/stable/"),
    ("proceedings.neurips.cc", "/paper"),
    ("papers.nips.cc", "/paper"),
    ("proceedings.mlr.press", "/v"),
    ("biorxiv.org", "/content/"),
    ("medrxiv.org", "/content/"),
    ("papers.ssrn.com", "/sol3/papers.cfm"),
    ("frontiersin.org", "/articles/"),
    ("academic.oup.com", "/"),
    ("journals.plos.org", "/"),
];

/// A link straight to a PDF (its path ends in .pdf): PaperLab downloads it, as a dropped PDF is uploaded.
pub fn is_pdf_link(link: &str) -> bool {
    let path = link.split(['?', '#']).next().unwrap_or(link);
    let lower = path.to_ascii_lowercase();
    (lower.starts_with("https://") || lower.starts_with("http://")) && lower.ends_with(".pdf")
}

/// A link that names a paper: a DOI in its path (most publishers' article links), or a paper site's article page.
pub fn names_a_paper(link: &str) -> bool {
    let Some((scheme, rest)) = link.trim().split_once("://") else { return false };
    if !matches!(scheme.to_ascii_lowercase().as_str(), "http" | "https") {
        return false;
    }
    let rest = rest.split(['?', '#']).next().unwrap_or(rest);
    let (authority, path) = rest.split_once('/').map_or((rest, ""), |(a, p)| (a, p));
    let host = authority.rsplit_once('@').map_or(authority, |(_, h)| h); // user@host
    let host = host.split(':').next().unwrap_or(host).trim_end_matches('.').to_ascii_lowercase(); // host:443, host.
    let path = format!("/{path}");
    // a DOI in the path: a "10.<4+ digit registrant>" segment, its suffix after it
    let registrant = |part: &str| {
        part.strip_prefix("10.").is_some_and(|r| {
            let digits_first = r.len() >= 4 && r.bytes().take(4).all(|b| b.is_ascii_digit());
            digits_first && r.bytes().all(|b| b.is_ascii_digit() || b == b'.')
        })
    };
    let segments: Vec<&str> = path.split('/').collect();
    let doi_inside = segments.windows(2).any(|pair| registrant(pair[0]) && !pair[1].is_empty());
    let on_site = |site: &str| host == site || host.ends_with(&format!(".{site}"));
    let article = |start: &str| path.starts_with(start) && path.len() > start.len();
    doi_inside || PAPER_PAGES.iter().any(|(site, start)| on_site(site) && article(start))
}

fn strip_prefix_ci<'a>(s: &'a str, prefixes: &[&str]) -> Option<&'a str> {
    prefixes.iter().find_map(|p| s.get(..p.len()).filter(|head| head.eq_ignore_ascii_case(p)).map(|_| &s[p.len()..]))
}

/// `10.<registrant>/<suffix>`, without a link's `?query` or `#fragment`, and with sentence punctuation a copy picks up
/// dropped from the end (a closing parenthesis only when it has no opening one in the DOI).
fn doi(s: &str) -> Option<String> {
    let s = s.split(['?', '#']).next().unwrap_or(s);
    let (registrant, suffix) = s.strip_prefix("10.")?.split_once('/')?;
    let ok = registrant.len() >= 4 && registrant.bytes().all(|b| b.is_ascii_digit() || b == b'.')
        && !suffix.is_empty() && !s.contains(char::is_whitespace);
    ok.then(|| trim_end_punctuation(s).to_owned())
}

fn trim_end_punctuation(mut s: &str) -> &str {
    loop {
        let t = s.trim_end_matches(['.', ',', ';', '"', '\'']);
        let unbalanced = t.ends_with(')') && t.matches('(').count() < t.matches(')').count();
        let t = if unbalanced { &t[..t.len() - 1] } else { t };
        if t == s {
            return s;
        }
        s = t;
    }
}

/// New style `2401.12345` (4 or 5 digits after the dot) or old style `hep-th/9901001`, either with `vN`.
fn arxiv_id(s: &str) -> bool {
    let s = match s.rsplit_once('v') {
        Some((id, n)) if !n.is_empty() && n.bytes().all(|b| b.is_ascii_digit()) => id,
        _ => s,
    };
    let digits = |t: &str| !t.is_empty() && t.bytes().all(|b| b.is_ascii_digit());
    if let Some((archive, num)) = s.split_once('/') {
        let archive = archive.split_once('.').map_or(archive, |(a, _)| a);
        return !archive.is_empty() && archive.bytes().all(|b| b.is_ascii_lowercase() || b == b'-')
            && num.len() == 7 && digits(num);
    }
    match s.split_once('.') {
        Some((yymm, num)) => yymm.len() == 4 && digits(yymm) && (4..=5).contains(&num.len()) && digits(num),
        None => false,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn dois_in_every_shape_a_copy_gives() {
        for raw in [
            "10.48550/arXiv.1706.03762",
            " https://doi.org/10.48550/arXiv.1706.03762 ",
            "doi.org/10.48550/arXiv.1706.03762",
            "DOI:10.48550/arXiv.1706.03762",
            "10.48550/arXiv.1706.03762.",
        ] {
            assert_eq!(classify(raw), Input::Doi("10.48550/arXiv.1706.03762".into()), "{raw}");
        }
        assert_eq!(classify("10.1000/xyz(2020)01"), Input::Doi("10.1000/xyz(2020)01".into()));
    }

    #[test]
    fn arxiv_ids_new_old_versioned_and_as_links() {
        for (raw, id) in [
            ("2401.12345", "2401.12345"),
            ("2401.12345v2", "2401.12345v2"),
            ("1706.0376", "1706.0376"),
            ("arXiv:1706.03762", "1706.03762"),
            ("https://arxiv.org/abs/1706.03762v7", "1706.03762v7"),
            ("https://arxiv.org/pdf/1706.03762.pdf", "1706.03762"),
            ("hep-th/9901001", "hep-th/9901001"),
            ("math.GT/0309136", "math.GT/0309136"),
        ] {
            assert_eq!(classify(raw), Input::Arxiv(id.into()), "{raw}");
        }
    }

    #[test]
    fn a_link_query_or_fragment_and_stray_punctuation_are_not_part_of_an_id() {
        let doi = |d: &str| Input::Doi(d.into());
        assert_eq!(classify("https://doi.org/10.48550/arXiv.1706.03762?utm_source=x"), doi("10.48550/arXiv.1706.03762"));
        assert_eq!(classify("https://doi.org/10.1234/abcd#section-2"), doi("10.1234/abcd"));
        assert_eq!(classify("10.1000/abc(x)"), doi("10.1000/abc(x)"));
        assert_eq!(classify("(see 10.1000/abc)"), Input::Text("(see 10.1000/abc)".into()));
        assert_eq!(classify("10.1000/abc)."), doi("10.1000/abc"));
        assert_eq!(classify("arXiv:2401.12345."), Input::Arxiv("2401.12345".into()));
        assert_eq!(classify("(2401.12345)"), Input::Arxiv("2401.12345".into()));
    }

    #[test]
    fn links_and_text_stay_what_they_are() {
        assert_eq!(classify("https://example.org/paper.pdf"), Input::Link("https://example.org/paper.pdf".into()));
        assert_eq!(classify("attention is all you need"), Input::Text("attention is all you need".into()));
        assert_eq!(classify("10.1 is a version"), Input::Text("10.1 is a version".into()));
        assert_eq!(classify("2401.123"), Input::Text("2401.123".into()));
        assert_eq!(classify("   "), Input::Empty);
        assert_eq!(classify("graph/1234567"), Input::Arxiv("graph/1234567".into()));
        assert_eq!(classify("and/or"), Input::Text("and/or".into()));
    }
}

#[cfg(test)]
mod paper_link_tests {
    use super::*;

    #[test]
    fn a_link_names_a_paper_by_a_doi_in_it_or_its_site() {
        assert!(names_a_paper("https://dl.acm.org/doi/10.1145/3292500.3330701"), "a DOI in the path");
        assert!(names_a_paper("https://link.springer.com/article/10.1007/s11263-015-0816-y"));
        assert!(names_a_paper("https://www.nature.com/articles/s41586-021-03819-2"), "Nature: no DOI, a paper site");
        assert!(names_a_paper("https://ieeexplore.ieee.org/document/9156610"));
        assert!(!names_a_paper("https://news.ycombinator.com/item?id=1"), "any other page: no");
        assert!(!names_a_paper("https://evilnature.com/x"), "a look-alike host: no");
        assert!(names_a_paper("HTTPS://WWW.Nature.com:443/articles/x"), "case and a port don't matter");
        assert!(names_a_paper("https://www.nature.com./articles/x"), "nor a trailing dot");
        assert!(!names_a_paper("https://www.nature.com/news/today"), "a paper site's other pages: no");
        assert!(!names_a_paper("https://dictionary.cambridge.org/dictionary/word"));
        assert!(!names_a_paper("https://nature.com@evil.example/articles/x"), "userinfo isn't the host");
        assert!(!names_a_paper("https://example.com/docs/10.12.1/guide"), "a version number isn't a DOI");
        assert!(!names_a_paper("ftp://nature.com/articles/x"));
        assert!(is_pdf_link("https://example.org/papers/Attention.PDF?download=1"));
        assert!(!is_pdf_link("https://example.org/papers/attention") && !is_pdf_link("file:///tmp/a.pdf"));
    }
}
