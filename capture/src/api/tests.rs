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

#[test]
fn a_reference_comes_back_as_its_text_and_an_error_as_its_sentence() {
    let api = fake(|_, path, body| match path {
        "/api/citations/export" if body.contains("\"bibtex\"") => (200, json!("@article{k, title={T}}")),
        "/api/citations/export" => (422, json!({ "detail": "unknown_format" })),
        _ => (404, json!({})),
    });
    assert_eq!(api.cite("p1", Format::Bibtex), Ok("\"@article{k, title={T}}\"".into()));
    assert_eq!(api.cite("p1", Format::Apa), Err(ApiError::Said("unknown_format".into())));
    assert!(matches!(cite::reference(b" \n"), Err(ApiError::Said(_))), "nothing to copy is an error");
}

#[test]
fn the_closest_papers_read_with_their_labels() {
    let api = fake(|_, _, _| {
        (200, json!({ "papers": [{ "paper_id": "p1", "title": "T", "year": 2020, "label": "very close",
            "distance": 0.1, "passage": "We show…", "page": 3, "section": null, "from_abstract": false,
            "chunk_id": "c" }], "searched_papers": 9, "note": "Only your library." }))
    });
    let found = api.novelty("an idea").unwrap();
    assert_eq!((found.papers[0].label.as_str(), found.papers[0].page, found.note.as_str()), ("very close", Some(3), "Only your library."));
}


fn heard_from(stream: &str) -> Vec<Said> {
    let mut heard = vec![];
    ask::read_events(stream.as_bytes(), |said| heard.push(said));
    heard
}

#[test]
fn an_answer_streams_as_sources_then_tokens_then_done_and_pings_are_skipped() {
    let stream = "event: sources\r\ndata: {\"whole_paper\":false,\"sources\":[{\"label\":\"C1\",\"paper_id\":\"p\",\"page\":4,\
                  \"chunk_id\":null,\"section\":null,\"bbox\":null,\"from_abstract\":false,\"replaced\":false}],\"notes\":[]}\r\n\r\n\
                  : ping\r\n\r\n\
                  event: token\r\ndata: {\"text\":\"Yes [C1]\"}\r\n\r\n\
                  event: token\r\ndata: {\"text\":\".\"}\r\n\r\n\
                  event: done\r\ndata: {\"output_id\":\"o\"}\r\n\r\n\
                  event: token\r\ndata: {\"text\":\"after the end\"}\r\n\r\n";
    let source = Source { label: "C1".into(), paper_id: "p".into(), page: 4 };
    assert_eq!(heard_from(stream), vec![Said::Sources(vec![source]), Said::Token("Yes [C1]".into()), Said::Token(".".into()), Said::Done]);
}

#[test]
fn an_answer_error_says_paperlabs_sentence_and_a_cut_stream_says_so() {
    let failed = heard_from("event: token\ndata: {\"text\":\"Half\"}\n\nevent: error\ndata: {\"message\":\"The model stopped.\",\"retryable\":true}\n\n");
    assert_eq!(failed, vec![Said::Token("Half".into()), Said::Failed("The model stopped.".into())]);
    let cut = heard_from("event: token\ndata: {\"text\":\"Half\"}\n\n");
    assert!(matches!(cut.as_slice(), [Said::Token(_), Said::Failed(_)]), "{cut:?}");
}

#[test]
fn workspaces_are_listed_and_a_refused_question_gives_paperlabs_sentence() {
    let api = fake(|_, path, _| match path {
        "/api/workspaces" => (200, json!([{ "id": "w", "name": "Thesis", "paper_count": 12, "note_count": 0 }])),
        _ => (503, json!({ "detail": "No model is set up yet." })),
    });
    assert_eq!(api.workspaces(), Ok(vec![Workspace { id: "w".into(), name: "Thesis".into(), paper_count: 12 }]));
    assert_eq!(api.ask("w", "why?", |_| {}), Err(ApiError::Said("No model is set up yet.".into())));
}

#[test]
fn sse_edge_cases_done_without_json_data_alone_multi_line_and_no_trailing_blank() {
    assert_eq!(heard_from("event: token\ndata: {\"text\":\"a\"}\n\nevent: done\ndata:\n\n"), vec![Said::Token("a".into()), Said::Done]);
    assert_eq!(heard_from("data: {\"stray\":1}\n\nevent: token\ndata: {\"text\":\"b\"}\n\nevent: done\ndata: {}\n\n"),
               vec![Said::Token("b".into()), Said::Done], "a data-only block doesn't leak into the next event");
    assert_eq!(heard_from("event: token\ndata: {\"text\":\ndata: \"c\"}\n\nevent: done\ndata: {}"),
               vec![Said::Token("c".into()), Said::Done], "lines join with a newline; the last event needs no blank line");
}

#[test]
fn an_upload_is_one_file_part_whose_name_cannot_break_its_header() {
    let body = String::from_utf8(upload::multipart("b0undary", "my \"paper\"\r\n.pdf", b"%PDF-1.7")).unwrap();
    assert!(body.contains("filename=\"my paper.pdf\""), "{body}");
    assert!(body.starts_with("--b0undary\r\n") && body.contains("application/pdf\r\n\r\n%PDF-1.7\r\n--b0undary--"), "{body}");
    assert!(body.ends_with("--\r\n"));
}

#[test]
fn an_unreadable_file_says_which() {
    let api = Api::new(9);
    let err = api.upload(std::path::Path::new("/no/such/dir/missing.pdf")).unwrap_err();
    assert!(matches!(err, ApiError::Said(s) if s.contains("missing.pdf")));
}
