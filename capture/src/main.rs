//! PaperLab Quick Capture (M65): a global shortcut opens a small panel over any app to find a paper in the library
//! or add one by DOI, arXiv ID or link. PaperLab's desktop app starts it with `--stdin` and the API's port.
//!
//! ```sh
//! cargo run -- --port 8000 --browser                # against the dev stack; ⌃⌥P opens the panel
//! cargo run -- --snap target/found.png --scene found  # headless still of one state (--list-scenes)
//! ```
//! stdin, with `--stdin`: `show` opens the panel, `quit` (or stdin closing) quits.

#![forbid(unsafe_code)]

mod api;
mod galaxy;
mod icon;
mod input;
mod library;
mod panel;
mod view;

use std::io::BufRead;
use std::process::Command;
use std::time::{Duration, Instant};

use rune::{Align, AppHandle, AppSpec, DisplayTarget, OverlayPlacement, ScreenEdge, TextEdit, WindowOptions, WindowSpec};

use api::Api;
use panel::{Effect, Event, Panel};

const BUNDLE_ID: &str = "io.github.khannoussi-malek.paperlab";
const DEFAULT_PORT: u16 = 5190;
const DEFAULT_SHORTCUT: &str = "ctrl+alt+p";
const POLL_EVERY: Duration = Duration::from_secs(1);

pub struct App {
    panel: Panel,
    query: TextEdit,
    /// None in tests: effects are kept in `sent` instead of performed.
    ctx: Option<Ctx>,
    sent: Vec<Effect>,
    /// PaperLab's icon in the header, decoded once.
    pub icon: rune::Pixels,
    /// When the shown list arrived; None after a failed fetch or an add, so the next show asks again.
    papers_at: Option<Instant>,
}

struct Ctx {
    me: AppHandle<App>,
    api: Api,
    /// `--browser`: open papers in this port's web app instead of the installed desktop app.
    browser: Option<u16>,
    /// The galaxy behind the panel (galaxy.rs); None where there's no screen.
    galaxy: Option<rune::OverlayHandle<galaxy::Galaxy>>,
}

impl App {
    fn new(ctx: Option<Ctx>) -> Self {
        App { panel: Panel::default(), query: focused(""), ctx, sent: vec![], icon: icon::pixels(), papers_at: None }
    }

    pub fn dispatch(&mut self, event: Event) {
        match &event {
            Event::Papers(Ok(_)) => self.papers_at = Some(Instant::now()),
            Event::Papers(Err(_)) | Event::AddDone(Ok(_)) => self.papers_at = None,
            _ => {}
        }
        for effect in self.panel.step(event) {
            self.perform(effect);
        }
    }

    pub fn close(&mut self) {
        if let Some(galaxy) = self.ctx.as_ref().and_then(|ctx| ctx.galaxy.as_ref()) {
            galaxy.update(|g, _| g.close());
            galaxy.fade_out(Duration::from_millis(250));
        }
        if let Some(ctx) = &self.ctx { ctx.me.close(); }
        self.dispatch(Event::Closed);
    }

    fn shown(&mut self) {
        if let Some(galaxy) = self.ctx.as_ref().and_then(|ctx| ctx.galaxy.as_ref()) {
            galaxy.update(|g, _| g.open());
            galaxy.show(); // before the panel, which then orders in above it
        }
        self.query = focused("");
        self.dispatch(Event::Shown);
    }

    fn perform(&mut self, effect: Effect) {
        if effect == Effect::FetchPapers && library::fresh(self.papers_at, Instant::now()) {
            return; // the list shown is under a minute old: no second download and parse
        }
        let Some(ctx) = &self.ctx else { return self.sent.push(effect) };
        let (me, api) = (ctx.me.clone(), ctx.api.clone());
        // ponytail: a thread per request; a handful per panel use, so a pool isn't worth it.
        match effect {
            Effect::FetchPapers => background(me, move || Event::Papers(api.papers())),
            Effect::Lookup { seq, query } => background(me, move || Event::Looked { seq, result: api.lookup(&query) }),
            Effect::Add { candidate, save_without_pdf } => {
                background(me, move || Event::AddDone(api.add(&candidate, save_without_pdf)));
            }
            Effect::Poll(id) => background(me, move || {
                std::thread::sleep(POLL_EVERY);
                let result = api.paper(&id);
                Event::Status { id, result }
            }),
            Effect::Open(id) => match ctx.browser {
                // Dev: the stack's own web app, so the paper opens in the library the panel searched.
                Some(port) => open(&[&format!("http://127.0.0.1:{port}/#/papers/{id}")]),
                None => open(&[&format!("paperlab://papers/{id}")]),
            },
            Effect::OpenPaperLab => match ctx.browser {
                Some(port) => open(&[&format!("http://127.0.0.1:{port}/")]),
                None => open(&["-b", BUNDLE_ID]),
            },
            Effect::Close => self.close(),
        }
    }
}

fn focused(text: &str) -> TextEdit {
    let mut edit = TextEdit::new(text);
    edit.focused = true;
    edit
}

fn background(me: AppHandle<App>, work: impl FnOnce() -> Event + Send + 'static) {
    std::thread::spawn(move || {
        let event = work();
        me.update(move |s, _| s.dispatch(event));
    });
}

fn open(args: &[&str]) {
    if let Err(e) = Command::new("open").args(args).spawn() {
        eprintln!("paperlab-capture: open {args:?} failed: {e}");
    }
}

fn show(me: &AppHandle<App>) {
    me.update(|s, _| s.shown());
    me.place(DisplayTarget::Primary, OverlayPlacement::Edge { edge: ScreenEdge::Top, margin: 150.0, align: Align::Center, inset: 0.0 });
    me.show();
}

struct Args {
    port: u16,
    shortcut: String,
    stdin: bool,
    browser: bool,
}

/// Our own flags; Rune's headless flags (`--snap`, `--scene`, …) pass through to Rune.
fn args() -> Result<Args, String> {
    let mut out = Args { port: DEFAULT_PORT, shortcut: DEFAULT_SHORTCUT.into(), stdin: false, browser: false };
    let mut argv = std::env::args().skip(1);
    while let Some(arg) = argv.next() {
        match arg.as_str() {
            "--port" => out.port = argv.next().and_then(|p| p.parse().ok()).ok_or("--port needs a number")?,
            "--shortcut" => out.shortcut = argv.next().ok_or("--shortcut needs a chord like ctrl+alt+p")?,
            "--stdin" => out.stdin = true,
            "--browser" => out.browser = true,
            _ => {}
        }
    }
    Ok(out)
}

fn main() {
    let args = args().unwrap_or_else(|e| {
        eprintln!("paperlab-capture: {e}");
        std::process::exit(2);
    });
    rune::run_windows(move |displays| {
        // The galaxy covers the main display, in points.
        let screen = displays.iter().find(|d| d.primary).or(displays.first())
            .map_or((1440.0, 900.0), |d| ((d.size.0 as f64 / d.scale) as f32, (d.size.1 as f64 / d.scale) as f32));
        let mut app = rune::App::new(AppSpec {
            scenes: scenes::ALL,
            ..AppSpec::new("Quick Capture", (view::WIDTH, 56.0), || unreachable!(), view::view)
        })
        .windowless()
        .accessory()
        .fit_content_height();
        let (me, api) = (app.handle(), Api::new(args.port));
        if args.stdin {
            let commands = app.handle();
            std::thread::spawn(move || {
                for line in std::io::stdin().lock().lines() {
                    match line.as_deref().map(str::trim) {
                        Ok("show") => show(&commands),
                        Ok("quit") | Err(_) => break,
                        Ok(other) => eprintln!("paperlab-capture: unknown command {other:?}"),
                    }
                }
                commands.quit(); // PaperLab quit or closed our stdin: go with it
            });
        }
        if !rune::is_headless() {
            // Warm the library before the first show: listing a big library takes seconds.
            background(me.clone(), { let api = api.clone(); move || Event::Papers(api.papers()) });
        }
        let galaxy = (!rune::is_headless()).then(|| app.overlay(galaxy::spec(screen), galaxy::Galaxy::new(screen)));
        let ctx = Ctx { me, api, browser: args.browser.then_some(args.port), galaxy };
        let app = app
            .init(move || App::new(Some(ctx)))
            .global_shortcut_named(&args.shortcut, "quick-capture", "Open PaperLab Quick Capture", |s, _| {
                if let Some(ctx) = &s.ctx { show(&ctx.me); }
            })
            .on_focus(|s, focused, _| if !focused { s.close() });
        [WindowSpec::from_app("capture", app).configured_options(WindowOptions::launcher_panel().macos(|native| native.shadow(true).corner_radius(14.0)))]
    });
}

/// Fixed states for `--snap` stills; they set the state through `Panel::step` and drop its effects.
mod scenes {
    use crate::App;
    use crate::api::{Added, Candidate, Found};
    use crate::library::Paper;
    use crate::panel::{Event, Panel};

    pub const ALL: &[(&str, fn(&mut App))] = &[
        ("library", |s| set(s, "", library_shown())),
        ("typed", |s| { let mut p = library_shown(); p.step(Event::Query("transformer".into())); set(s, "transformer", p) }),
        ("looking-up", |s| set(s, "10.48550/arXiv.1706.03762", looked_up(None))),
        ("found", |s| set(s, "10.48550/arXiv.1706.03762", looked_up(Some(Ok(found()))))),
        ("adding", |s| set(s, "2401.12345", added(None))),
        ("added", |s| set(s, "2401.12345", added(Some(Added::Queued(paper("n", "Retrieval-augmented reading of long papers", "embedding")))))),
        ("no-free-pdf", |s| set(s, "2401.12345", added(Some(Added::NoFreePdf("No free PDF was found for this paper. Open its page, download the PDF and use Upload PDFs.".into()))))),
        ("offline", |s| { let mut p = Panel::default(); p.step(Event::Papers(Err(crate::api::ApiError::Unreachable))); set(s, "", p) }),
    ];

    fn set(s: &mut App, query: &str, panel: Panel) {
        s.query = crate::focused(query);
        s.panel = panel;
    }

    fn paper(id: &str, title: &str, status: &str) -> Paper {
        Paper { id: id.into(), title: title.into(), authors: vec!["Ana Lopez".into(), "Wei Zhang".into(), "Sam Okafor".into()],
                year: Some(2024), doi: None, status: status.into(), status_error: None, created_at: format!("2026-11-{id}") }
    }

    fn library_shown() -> Panel {
        let mut p = Panel::default();
        p.step(Event::Shown);
        p.step(Event::Papers(Ok(vec![
            paper("01", "Attention Is All You Need", "ready"),
            paper("02", "BERT: Pre-training of Deep Bidirectional Transformers", "ready"),
            paper("03", "Retrieval-Augmented Generation for Knowledge-Intensive NLP", "ready"),
            paper("04", "Scaling Laws for Neural Language Models", "ready"),
            paper("05", "An Image is Worth 16x16 Words: Transformers for Image Recognition", "ready"),
        ])));
        p
    }

    fn candidate(title: &str, paper_id: Option<&str>) -> Candidate {
        Candidate { title: title.into(), authors: vec!["Ashish Vaswani".into(), "Noam Shazeer".into(), "Niki Parmar".into()],
                    year: Some(2017), paper_id: paper_id.map(Into::into), raw: serde_json::json!({ "title": title }) }
    }

    fn found() -> Found {
        Found { results: vec![candidate("Attention Is All You Need", None)],
                notices: vec!["Semantic Scholar is busy or unreachable.".into()] }
    }

    fn looked_up(answer: Option<Result<Found, crate::api::ApiError>>) -> Panel {
        let mut p = library_shown();
        p.step(Event::Query("10.48550/arXiv.1706.03762".into()));
        if let Some(result) = answer { p.step(Event::Looked { seq: 1, result }); }
        p
    }

    fn added(answer: Option<Added>) -> Panel {
        let mut p = library_shown();
        p.step(Event::Query("2401.12345".into()));
        let found = Found { results: vec![candidate("Retrieval-augmented reading of long papers", None)], notices: vec![] };
        p.step(Event::Looked { seq: 1, result: Ok(found) });
        p.step(Event::Submit);
        if let Some(answer) = answer { p.step(Event::AddDone(Ok(answer))); }
        p
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use rune::{Env, Key, KeyEvent, Mods, Runtime};

    fn runtime() -> Runtime<App> {
        let mut rt = Runtime::new(App::new(None), view::view, (view::WIDTH, 400.0), Env { system_dark: true, scale: 2.0 });
        rt.state.dispatch(Event::Shown);
        rt.state.dispatch(Event::Papers(Ok(vec![
            library::paper("a", "Attention Is All You Need", &["Ashish Vaswani"], 2017, "2026-01"),
            library::paper("b", "Graph attention networks", &["Petar Velickovic"], 2018, "2026-02"),
        ])));
        rt.state.sent.clear();
        rt.frame(0.0);
        rt
    }

    fn press(rt: &mut Runtime<App>, key: Key) {
        rt.key(KeyEvent { key, mods: Mods::default() });
        rt.frame(1.0 / 60.0);
    }

    #[test]
    fn typing_filters_and_enter_opens_the_picked_paper() {
        let mut rt = runtime();
        assert!(rt.find("row-1").is_some(), "two newest papers listed");
        rt.paste("graph");
        rt.frame(1.0 / 60.0);
        assert!(rt.find("row-0").is_some() && rt.find("row-1").is_some() && rt.find("row-2").is_none(),
                "one paper and Search online");
        press(&mut rt, Key::Enter);
        assert_eq!(rt.state.sent, vec![Effect::Open("b".into()), Effect::Close]);
    }

    #[test]
    fn a_pasted_doi_is_looked_up_and_down_moves_the_pick() {
        let mut rt = runtime();
        press(&mut rt, Key::Down);
        assert_eq!(rt.state.panel.picked, 1);
        rt.paste("https://doi.org/10.48550/arXiv.1706.03762");
        rt.frame(1.0 / 60.0);
        assert_eq!(rt.state.sent, vec![Effect::Lookup { seq: 1, query: "10.48550/arXiv.1706.03762".into() }]);
        assert!(rt.find("status").is_some(), "Looking up… is shown");
    }

    #[test]
    fn escape_closes() {
        let mut rt = runtime();
        press(&mut rt, Key::Escape);
        assert_eq!(rt.state.panel.query, "");
        assert!(rt.state.sent.is_empty(), "no effect beyond the close itself");
    }

    #[test]
    fn every_scene_renders() {
        for (name, set) in scenes::ALL {
            let mut rt = runtime();
            set(&mut rt.state);
            rt.frame(1.0 / 60.0);
            assert!(rt.find("panel").is_some(), "{name}");
        }
    }
}
