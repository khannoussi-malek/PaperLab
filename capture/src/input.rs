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
