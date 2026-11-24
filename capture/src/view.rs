//! What the panel draws for a `Panel` state: the field, one line saying what's happening, and the rows Enter acts on.

use rune::tok::{self, type_};
use rune::{Color, Cx, El, Key, KeyEvent, SystemMaterial, Tx, col, el, row, text, text_input};

use crate::App;
use crate::library::{Paper, byline};
use crate::panel::{Event, Phase, Row, UNREACHABLE};

pub const WIDTH: f32 = 600.0;

/// The blue of PaperLab's icon, for the light behind it in the header.
fn logo_blue() -> Color {
    rune::color::hex("#2664ee").expect("a valid colour")
}

pub fn view(app: &App, cx: &mut Cx<App>) -> El {
    let dark = cx.system_dark();
    let t = tok::theme(dark);
    let p = &app.panel;
    let field = text_input(&app.query, type_::BODY.lh(26.0)).key("query").single_line().grow(1.0)
        .color(t.text).placeholder("Find a paper, or paste a DOI, arXiv ID or link", t.text_secondary)
        .on_edit(|s: &mut App| &mut s.query)
        .on_input_change(|s: &mut App, _| { let q = s.query.text.clone(); s.dispatch(Event::Query(q)); })
        .on_input_key(|s: &mut App, ev: &KeyEvent, _: &mut Tx| {
            match ev.key {
                Key::Down => s.dispatch(Event::Down),
                Key::Up => s.dispatch(Event::Up),
                Key::Escape => s.close(),
                _ => return false,
            }
            true
        })
        .on_submit(|s: &mut App, _| s.dispatch(Event::Submit));
    // Liquid Glass over whatever is behind the window (the card colour where glass can't show: older macOS, headless).
    let glow = logo_blue().alpha(if dark { 0.34 } else { 0.2 });
    let mut panel = col().key("panel").w(WIDTH).radius(14.0).clip_rounded(14.0).fill(t.card)
        .system_material(SystemMaterial::Glass)
        .border(1.0, if dark { Color::WHITE.alpha(0.1) } else { t.separator })
        .child(row().h(56.0).px(18.0).gap(12.0).center_y()
            // A soft light in the logo's blue, centred on the icon and fading out across the field.
            .radial_gradient([31.0, 28.0], [220.0, 72.0], [(0.0, glow), (1.0, glow.alpha(0.0))])
            .child(el().size(26.0, 26.0).radius(6.0).pixels(&app.icon))
            .child(field));
    let status = status_line(p);
    let rows = p.rows();
    if status.is_some() || !rows.is_empty() {
        panel = panel.child(el().h(1.0).w_full().fill(t.separator));
    }
    if let Some(line) = status {
        panel = panel.child(row().key("status").px(18.0).py(10.0)
            .child(text(line).font(type_::LABEL).color(t.text_secondary).w_full()));
    }
    if !rows.is_empty() {
        let mut list = col().key("rows").padding(6.0).gap(2.0);
        for (i, r) in rows.iter().enumerate() {
            let on = i == p.picked;
            let (title, detail) = row_text(p, r);
            let ink = if on { Color::WHITE } else { t.text };
            let mut line = row().key(format!("row-{i}")).h(48.0).px(12.0).gap(12.0).radius(8.0).center_y()
                .fill(if on { tok::accent(0, dark).alpha(0.9) } else { Color::TRANSPARENT })
                .child(col().grow(1.0).shrink().gap(2.0)
                    .child(text(title).font(type_::BODY).color(ink).truncate())
                    .child(text(detail).font(type_::LABEL).color(if on { ink.alpha(0.8) } else { t.text_secondary }).truncate()));
            if let Some(badge) = badge(p, r) {
                line = line.child(text(badge).font(type_::LABEL).color(if on { ink } else { t.text_secondary }));
            }
            list = list.child(line);
        }
        panel = panel.child(list);
    }
    col().w_full().child(panel)
}

fn status_line(p: &crate::panel::Panel) -> Option<String> {
    match &p.phase {
        Phase::Library => None,
        Phase::LookingUp(q) => Some(format!("Looking up {q}…")),
        Phase::Found(f) if f.results.is_empty() => Some(join("Nothing found.", &f.notices)),
        Phase::Found(f) => (!f.notices.is_empty()).then(|| f.notices.join(" ")),
        Phase::Adding(c) => Some(format!("Adding “{}”…", c.title)),
        Phase::Added(paper) => Some(progress(paper)),
        Phase::NoFreePdf { message, .. } => Some(message.clone()),
        Phase::Failed(sentence) => Some(sentence.clone()),
    }
}

fn row_text(p: &crate::panel::Panel, r: &Row) -> (String, String) {
    match r {
        Row::Paper(i) => {
            let paper = &p.papers[*i];
            (paper.title.clone(), byline(&paper.authors, paper.year))
        }
        Row::SearchOnline(q) => (format!("Search online for “{q}”"), "Asks every paper source that's on".into()),
        Row::Candidate(i) => {
            let Phase::Found(f) = &p.phase else { return Default::default() };
            let c = &f.results[*i];
            (c.title.clone(), byline(&c.authors, c.year))
        }
        Row::SaveWithoutPdf => ("Save without PDF".into(), "Keeps its details and abstract; add the PDF later".into()),
        Row::OpenAdded(_) => match &p.phase {
            Phase::Added(paper) => (paper.title.clone(), "Open in PaperLab".into()),
            _ => Default::default(),
        },
        Row::OpenPaperLab => ("Open PaperLab".into(), UNREACHABLE.into()),
    }
}

fn badge(p: &crate::panel::Panel, r: &Row) -> Option<&'static str> {
    match (r, &p.phase) {
        (Row::Candidate(i), Phase::Found(f)) => Some(if f.results[*i].paper_id.is_some() { "In your library" } else { "Add ↵" }),
        (Row::Paper(_) | Row::OpenAdded(_), _) => Some("Open ↵"),
        _ => None,
    }
}

/// The added paper's ingest status in words.
fn progress(paper: &Paper) -> String {
    match paper.status.as_str() {
        "ready" => "Ready.".into(),
        "failed" => format!("Couldn't read it: {}", paper.status_error.as_deref().unwrap_or("no reason given.")),
        "uploaded" => "Added, waiting its turn…".into(),
        "extracting" => "Reading the PDF…".into(),
        "chunking" | "embedding" => "Indexing for search…".into(),
        "enriching" => "Filling in its details…".into(),
        other => format!("{other}…"),
    }
}

fn join(head: &str, notices: &[String]) -> String {
    std::iter::once(head).chain(notices.iter().map(String::as_str)).collect::<Vec<_>>().join(" ")
}
