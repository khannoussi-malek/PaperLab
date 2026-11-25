use super::*;
use serde_json::json;
use std::io::{BufRead, BufReader, Read, Write};
use std::net::TcpListener;

/// A one-request-per-connection fake PaperLab: `answer(method, path_and_query, body)` gives (status, json).
fn fake(answer: impl Fn(&str, &str, &str) -> (u16, Value) + Send + 'static) -> Api {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let port = listener.local_addr().unwrap().port();
    std::thread::spawn(move || {
        for stream in listener.incoming() {
            let mut stream = stream.unwrap();
            let mut reader = BufReader::new(stream.try_clone().unwrap());
            let (mut line, mut length) = (String::new(), 0);
            reader.read_line(&mut line).unwrap();
            let mut parts = line.split_whitespace();
            let (method, target) = (parts.next().unwrap().to_owned(), parts.next().unwrap().to_owned());
            loop {
                let mut header = String::new();
                reader.read_line(&mut header).unwrap();
                if header.trim().is_empty() { break; }
                if let Some(v) = header.to_lowercase().strip_prefix("content-length:") { length = v.trim().parse().unwrap(); }
            }
            let mut body = vec![0; length];
            reader.read_exact(&mut body).unwrap();
            let (status, json) = answer(&method, &target, &String::from_utf8(body).unwrap());
            let json = json.to_string();
            write!(stream, "HTTP/1.1 {status} X\r\ncontent-type: application/json\r\ncontent-length: {}\r\nconnection: close\r\n\r\n{json}", json.len()).unwrap();
        }
    });
    Api::new(port)
}

fn paper_json(id: &str, status: &str) -> Value {
    json!({ "id": id, "title": "Attention Is All You Need", "authors": ["Ashish Vaswani"], "year": 2017,
            "doi": null, "status": status, "created_at": "2026-11-24T00:00:00Z", "abstract": "ignored" })
}

#[test]
fn papers_and_one_paper() {
    let api = fake(|_, path, _| match path {
        "/api/papers/brief" => (200, json!([paper_json("p1", "ready")])),
        "/api/papers/p1" => (200, paper_json("p1", "embedding")),
        _ => (404, json!({ "detail": "paper_not_found" })),
    });
    assert_eq!(api.papers().unwrap()[0].id, "p1");
    assert_eq!(api.paper("p1").unwrap().status, "embedding");
    assert_eq!(api.paper("nope"), Err(ApiError::Said("paper_not_found".into())));
}

#[test]
fn lookup_sends_the_query_and_keeps_notices() {
    let api = fake(|_, path, _| {
        assert_eq!(path, "/api/discovery/search?q=10.48550%2FarXiv.1706.03762");
        (200, json!({ "results": [{ "title": "Attention", "authors": ["A B"], "year": 2017, "paper_id": "p9",
                                    "sources": ["arxiv"] }],
                      "notices": ["Semantic Scholar is busy or unreachable."] }))
    });
    let found = api.lookup("10.48550/arXiv.1706.03762").unwrap();
    assert_eq!(found.results[0].paper_id.as_deref(), Some("p9"));
    assert_eq!(found.results[0].raw["sources"], json!(["arxiv"]));
    assert_eq!(found.notices.len(), 1);
}

#[test]
fn add_tells_queued_in_library_no_pdf_and_other_errors_apart() {
    let api = fake(|_, _, body| {
        let sent: Value = serde_json::from_str(body).unwrap();
        assert_eq!(sent["candidate"]["sources"], json!(["arxiv"]), "the candidate goes back as it came");
        match sent["candidate"]["title"].as_str().unwrap() {
            "new" if sent["save_without_pdf"] == json!(false) => (201, paper_json("p2", "uploaded")),
            "have" => (409, json!({ "detail": "This paper is already in your library.", "paper_id": "p1", "tried": [] })),
            "paywalled" => (409, json!({ "detail": "No free PDF was found for this paper.", "tried": [], "free_copies": [] })),
            _ => (409, json!({ "detail": "No paper source that can look this up is on." })),
        }
    });
    let c = |title: &str| Candidate { title: title.into(), authors: vec![], year: None, paper_id: None,
                                      raw: json!({ "title": title, "sources": ["arxiv"] }) };
    assert!(matches!(api.add(&c("new"), false), Ok(Added::Queued(p)) if p.id == "p2"));
    assert_eq!(api.add(&c("have"), false), Ok(Added::AlreadyInLibrary("p1".into())));
    assert_eq!(api.add(&c("paywalled"), false), Ok(Added::NoFreePdf("No free PDF was found for this paper.".into())));
    assert_eq!(api.add(&c("other"), false), Err(ApiError::Said("No paper source that can look this up is on.".into())));
}

#[test]
fn nothing_listening_is_unreachable() {
    let port = TcpListener::bind("127.0.0.1:0").unwrap().local_addr().unwrap().port();
    assert_eq!(Api::new(port).papers(), Err(ApiError::Unreachable));
}
