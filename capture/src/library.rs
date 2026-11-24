//! The reader's papers, kept in memory, and the title/author/year filter the panel shows as they type.

use serde::Deserialize;

/// The fields of `PaperOut` the panel uses; the rest of each paper is ignored.
#[derive(Clone, Debug, PartialEq, Deserialize)]
pub struct Paper {
    pub id: String,
    pub title: String,
    #[serde(default)]
    pub authors: Vec<String>,
    pub year: Option<i32>,
    pub doi: Option<String>,
    pub status: String,
    #[serde(default)]
    pub status_error: Option<String>,
    #[serde(default)]
    pub created_at: String,
}

pub const SHOWN: usize = 8;

/// How long a fetched list is reused when the panel opens again: a big library's list costs seconds and a memory peak.
pub const LIST_MAX_AGE: std::time::Duration = std::time::Duration::from_secs(60);

/// Whether a list fetched at `fetched` can still be shown at `now` without asking again.
pub fn fresh(fetched: Option<std::time::Instant>, now: std::time::Instant) -> bool {
    fetched.is_some_and(|at| now.saturating_duration_since(at) < LIST_MAX_AGE)
}

/// Up to `SHOWN` papers for `query`, best first: newest when it's empty; otherwise every word must appear in the
/// title, an author or the year, and a title that starts with the query ranks above one that contains it.
pub fn matching(papers: &[Paper], query: &str) -> Vec<usize> {
    let q = query.trim().to_lowercase();
    let mut hits: Vec<(u8, usize)> = papers.iter().enumerate()
        .filter_map(|(i, p)| rank(p, &q).map(|r| (r, i)))
        .collect();
    // ponytail: a linear scan per keystroke; fine for thousands of papers, index titles if a library gets huge.
    hits.sort_by(|a, b| a.0.cmp(&b.0).then_with(|| papers[b.1].created_at.cmp(&papers[a.1].created_at)));
    hits.into_iter().take(SHOWN).map(|(_, i)| i).collect()
}

fn rank(p: &Paper, q: &str) -> Option<u8> {
    if q.is_empty() {
        return Some(0);
    }
    let title = p.title.to_lowercase();
    if title.starts_with(q) {
        return Some(0);
    }
    if title.contains(q) {
        return Some(1);
    }
    let hay = format!("{title} {} {}", p.authors.join(" ").to_lowercase(), p.year.map_or(String::new(), |y| y.to_string()));
    q.split_whitespace().all(|w| hay.contains(w)).then_some(2)
}

/// "Vaswani, Shazeer et al. · 2017"
pub fn byline(authors: &[String], year: Option<i32>) -> String {
    let surname = |a: &String| a.rsplit(' ').next().unwrap_or(a).to_owned();
    let who = match authors {
        [] => String::new(),
        [a] => surname(a),
        [a, b] => format!("{}, {}", surname(a), surname(b)),
        [a, b, ..] => format!("{}, {} et al.", surname(a), surname(b)),
    };
    match (who.is_empty(), year) {
        (false, Some(y)) => format!("{who} · {y}"),
        (true, Some(y)) => y.to_string(),
        _ => who,
    }
}

#[cfg(test)]
pub fn paper(id: &str, title: &str, authors: &[&str], year: i32, created_at: &str) -> Paper {
    Paper {
        id: id.into(), title: title.into(), authors: authors.iter().map(|a| a.to_string()).collect(),
        year: Some(year), doi: None, status: "ready".into(), status_error: None, created_at: created_at.into(),
    }
}

#[cfg(test)]
mod tests {
    use std::time::{Duration, Instant};

    #[test]
    fn a_list_is_reused_for_a_minute_then_fetched_again() {
        let at = Instant::now();
        assert!(!super::fresh(None, at));
        assert!(super::fresh(Some(at), at + Duration::from_secs(59)));
        assert!(!super::fresh(Some(at), at + Duration::from_secs(60)));
    }

    use super::*;

    fn library() -> Vec<Paper> {
        vec![
            paper("a", "Attention Is All You Need", &["Ashish Vaswani", "Noam Shazeer"], 2017, "2026-01-01"),
            paper("b", "Self-attention in vision transformers", &["Ana Lopez"], 2021, "2026-03-01"),
            paper("c", "BERT: pre-training of deep transformers", &["Jacob Devlin"], 2019, "2026-02-01"),
        ]
    }

    #[test]
    fn empty_query_shows_newest_first() {
        assert_eq!(matching(&library(), "  "), vec![1, 2, 0]);
    }

    #[test]
    fn title_start_beats_contains_beats_scattered_words() {
        let lib = library();
        assert_eq!(matching(&lib, "attention"), vec![0, 1]);
        assert_eq!(matching(&lib, "transformers devlin"), vec![2]);
        assert_eq!(matching(&lib, "vaswani 2017"), vec![0]);
        assert!(matching(&lib, "diffusion").is_empty());
    }

    #[test]
    fn at_most_eight() {
        let lib: Vec<Paper> = (0..20).map(|i| paper(&i.to_string(), "Graphs", &[], 2020, "2026")).collect();
        assert_eq!(matching(&lib, "graphs").len(), SHOWN);
    }

    #[test]
    fn bylines() {
        let names = |v: &[&str]| v.iter().map(|a| a.to_string()).collect::<Vec<_>>();
        assert_eq!(byline(&names(&["Ashish Vaswani", "Noam Shazeer", "Niki Parmar"]), Some(2017)), "Vaswani, Shazeer et al. · 2017");
        assert_eq!(byline(&names(&["Jacob Devlin"]), None), "Devlin");
        assert_eq!(byline(&[], Some(2019)), "2019");
    }
}
