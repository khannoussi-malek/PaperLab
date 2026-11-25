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
mod clipboard;
mod bubbles;
mod float;
mod galaxy;
mod icon;
mod input;
mod library;
mod mode;
mod panel;
mod scenes;
mod view;

use std::io::BufRead;
use std::process::Command;
use std::time::{Duration, Instant};

use rune::{Align, AppHandle, AppSpec, DisplayTarget, OverlayPlacement, ScreenEdge, TextEdit, WindowOptions, WindowSpec};

use api::{Api, ApiError};
use panel::{Effect, Event, Panel};

const BUNDLE_ID: &str = "io.github.khannoussi-malek.paperlab";
const DEFAULT_PORT: u16 = 5190;
const DEFAULT_SHORTCUT: &str = "ctrl+alt+p";
const POLL_EVERY: Duration = Duration::from_secs(1);
/// How often the floating paper looks for something new (free PDFs found, new saved-search results), so its badge
/// also drops soon after the owner handles them inside PaperLab.
const INBOX_EVERY: Duration = Duration::from_secs(5 * 60);
/// How long "Copied …" stays before the panel closes by itself.
const CONFIRM_FOR: Duration = Duration::from_millis(900);

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
    /// The floating paper (float.rs, `--float`), told when the panel closes so it floats again.
    float: Option<rune::OverlayHandle<float::Float>>,
}

impl App {
    fn new(ctx: Option<Ctx>) -> Self {
        App { panel: Panel::default(), query: focused(""), ctx, sent: vec![], icon: icon::pixels(), papers_at: None }
    }

    pub fn dispatch(&mut self, event: Event) {
        match &event {
            Event::Papers(Ok(_)) => self.papers_at = Some(Instant::now()),
            Event::Papers(Err(_)) | Event::AddDone { result: Ok(_), .. } => self.papers_at = None,
            Event::Inbox(Ok(inbox)) => self.badge(inbox.count()),
            _ => {}
        }
        for effect in self.panel.step(event) {
            self.perform(effect);
        }
        // The panel owns the text: when it changes it (an answer's question back, a note's field emptied once its
        // paper is picked), the field follows. Typing leaves them equal, so the caret never jumps.
        if self.panel.query != self.query.text {
            self.query = focused(&self.panel.query);
        }
    }

    /// The floating paper's badge: what the Inbox holds.
    fn badge(&self, count: usize) {
        if let Some(float) = self.ctx.as_ref().and_then(|ctx| ctx.float.as_ref()) {
            float.update(move |f, _| f.badge = count);
        }
    }

    pub fn close(&mut self) {
        if let Some(float) = self.ctx.as_ref().and_then(|ctx| ctx.float.as_ref()) {
            float.update(|f, _| f.panel_closed());
        }
        if let Some(galaxy) = self.ctx.as_ref().and_then(|ctx| ctx.galaxy.as_ref()) {
            galaxy.update(|g, _| g.close());
            galaxy.fade_out(Duration::from_millis(250));
        }
        if let Some(ctx) = &self.ctx { ctx.me.close(); }
        self.dispatch(Event::Closed);
    }

    /// Opened by the shortcut: in Find, with the galaxy behind it. Opened from the floating paper: in the mode its
    /// bubble picked (None: the last one used, for a drop), with `query` typed in (the clipboard's paper), and without
    /// the galaxy (the bubbles were the animation, and the user wants the function).
    fn shown(&mut self, mode: Option<mode::Mode>, galaxy: bool, query: Option<String>) {
        if let Some(galaxy) = self.ctx.as_ref().and_then(|ctx| ctx.galaxy.as_ref()).filter(|_| galaxy) {
            galaxy.update(|g, _| g.open());
            galaxy.show(); // before the panel, which then orders in above it
        }
        if let Some(mode) = mode {
            self.panel.mode = mode;
        }
        self.dispatch(Event::Shown);
        if let Some(query) = query {
            self.dispatch(Event::Query(query));
        }
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
            Effect::Add { seq, candidate, save_without_pdf } => {
                background(me, move || Event::AddDone { seq, result: api.add(&candidate, save_without_pdf) });
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
            Effect::CloseSoon(seq) => background(me, move || {
                std::thread::sleep(CONFIRM_FOR);
                Event::CloseNow(seq)
            }),
            Effect::PutInWorkspace { seq, workspace_id, paper_id } => background(me, move || {
                let result = api.put_in_workspace(&workspace_id, &paper_id);
                Event::Put { seq, workspace_id, result }
            }),
            Effect::SaveNote { seq, paper_id, body } => {
                background(me, move || Event::NoteSaved { seq, result: api.note(&paper_id, &body) });
            }
            Effect::Cite { seq, paper_id, title, format } => background(me, move || {
                let result = api.cite(&paper_id, format).and_then(|text| copy(&text));
                Event::Copied { seq, what: format!("{} of “{title}”", format.label()), result }
            }),
            Effect::FetchWorkspaces => background(me, move || Event::Workspaces(api.workspaces())),
            Effect::Ask { seq, workspace_id, question } => {
                std::thread::spawn(move || {
                    let hear = me.clone();
                    let heard = move |said| hear.update(move |s, _| s.dispatch(Event::Heard { seq, result: Ok(said) }));
                    if let Err(e) = api.ask(&workspace_id, &question, heard) {
                        me.update(move |s, _| s.dispatch(Event::Heard { seq, result: Err(e) }));
                    }
                });
            }
            Effect::OpenWorkspace { id, tab } => match ctx.browser {
                Some(port) => open(&[&format!("http://127.0.0.1:{port}/#/workspaces/{id}?tab={tab}")]),
                None => open(&[&format!("paperlab://workspaces/{id}?tab={tab}")]),
            },
            Effect::FetchInbox => background(me, move || Event::Inbox(api.inbox())),
            Effect::FoundSeen(id) => background(me, move || {
                if let Err(e) = api.found_seen(&id) {
                    eprintln!("paperlab-capture: couldn't mark a found PDF seen: {e:?}");
                }
                Event::Inbox(api.inbox()) // the badge drops by one
            }),
            Effect::Copy { seq, text, what } => background(me, move || Event::Copied { seq, what, result: copy(&text) }),
            Effect::Upload { seq, paths } => background(me, move || {
                let results = paths.iter().map(|path| api.upload(path)).collect();
                Event::Uploaded { seq, results }
            }),
            Effect::Novelty { seq, text } => background(me, move || Event::Novelty { seq, result: api.novelty(&text) }),
        }
    }
}

fn focused(text: &str) -> TextEdit {
    let mut edit = TextEdit::new(text);
    edit.focused = true;
    edit
}

/// Lists the Inbox now and every INBOX_EVERY after, for the floating paper's badge (App::dispatch passes it on).
fn keep_inbox_fresh(me: AppHandle<App>, api: Api) {
    std::thread::spawn(move || loop {
        let result = api.inbox();
        me.update(move |s, _| s.dispatch(Event::Inbox(result)));
        std::thread::sleep(INBOX_EVERY);
    });
}

fn background(me: AppHandle<App>, work: impl FnOnce() -> Event + Send + 'static) {
    std::thread::spawn(move || {
        let event = work();
        me.update(move |s, _| s.dispatch(event));
    });
}

fn copy(text: &str) -> Result<(), ApiError> {
    clipboard::copy(text).map_err(|e| ApiError::Said(format!("Couldn't copy it to the clipboard ({e}).")))
}

fn open(args: &[&str]) {
    if let Err(e) = Command::new("open").args(args).spawn() {
        eprintln!("paperlab-capture: open {args:?} failed: {e}");
    }
}

/// Opens the panel beside the floating paper, at `at` (its top-left on the main display, in points), in `mode` (None:
/// the last one used), with `query` typed in.
fn show_at(me: &AppHandle<App>, at: (f32, f32), mode: Option<mode::Mode>, query: Option<String>) {
    me.update(move |s, _| s.shown(mode, false, query));
    me.place(DisplayTarget::Primary, OverlayPlacement::Rect { x: at.0, y: at.1, width: view::WIDTH, height: 56.0 });
    me.show();
}

fn show(me: &AppHandle<App>) {
    me.update(|s, _| s.shown(Some(mode::Mode::Find), true, None));
    me.place(DisplayTarget::Primary, OverlayPlacement::Edge { edge: ScreenEdge::Top, margin: 150.0, align: Align::Center, inset: 0.0 });
    me.show();
}

struct Args {
    port: u16,
    shortcut: String,
    stdin: bool,
    browser: bool,
    /// `--no-galaxy`: the panel alone, no stars or papers behind it (Settings → Desktop app → Animation).
    galaxy: bool,
    /// `--float` (M79 spike): a paper floating over every app, bottom right.
    float: bool,
}

/// Our own flags; Rune's headless flags (`--snap`, `--scene`, …) pass through to Rune.
fn args() -> Result<Args, String> {
    let mut out = Args { port: DEFAULT_PORT, shortcut: DEFAULT_SHORTCUT.into(), stdin: false, browser: false, galaxy: true, float: false };
    let mut argv = std::env::args().skip(1);
    while let Some(arg) = argv.next() {
        match arg.as_str() {
            "--port" => out.port = argv.next().and_then(|p| p.parse().ok()).ok_or("--port needs a number")?,
            "--shortcut" => out.shortcut = argv.next().ok_or("--shortcut needs a chord like ctrl+alt+p")?,
            "--stdin" => out.stdin = true,
            "--browser" => out.browser = true,
            "--no-galaxy" => out.galaxy = false,
            "--float" => out.float = true,
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
        let screen = displays.iter().find(|d| d.primary).or(displays.first()).filter(|d| d.scale > 0.0)
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
        let galaxy = (args.galaxy && !rune::is_headless())
            .then(|| app.overlay(galaxy::spec(screen), galaxy::Galaxy::new(screen)));
        let float = (args.float && !rune::is_headless()).then(|| {
            let state = float::Float::new(Some(me.clone()), screen);
            let handle = app.overlay(float::spec(state.origin()), state);
            let own = handle.clone();
            handle.update(move |s, _| s.handle = Some(own)); // so a drag can move its own overlay
            handle.show();
            keep_inbox_fresh(me.clone(), api.clone()); // the paper's badge
            handle
        });
        let ctx = Ctx { me, api, browser: args.browser.then_some(args.port), galaxy, float };
        let app = app
            .init(move || App::new(Some(ctx)))
            .global_shortcut_named(&args.shortcut, "quick-capture", "Open PaperLab Quick Capture", |s, _| {
                if let Some(ctx) = &s.ctx {
                    if let Some(float) = &ctx.float {
                        float.update(|f, _| f.unhide()); // hidden for an hour: the shortcut brings it back
                    }
                    show(&ctx.me);
                }
            })
            .on_focus(|s, focused, _| if !focused { s.close() });
        [WindowSpec::from_app("capture", app).configured_options(WindowOptions::launcher_panel().macos(|native| native.shadow(true).corner_radius(14.0)))]
    });
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
    fn opened_with_the_copied_paper_it_is_typed_in_find_and_looked_up() {
        let mut rt = runtime();
        rt.state.panel.mode = mode::Mode::Ask;
        rt.update(|s, _| s.shown(Some(mode::Mode::Find), false, Some("10.48550/arXiv.1706.03762".into())));
        rt.frame(1.0 / 60.0);
        assert_eq!(rt.state.panel.mode, mode::Mode::Find);
        assert!(rt.state.sent.contains(&Effect::Lookup { seq: 1, query: "10.48550/arXiv.1706.03762".into() }));
        assert_eq!(rt.state.query.text, "10.48550/arXiv.1706.03762", "the field shows what's looked up");
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

    fn command(rt: &mut Runtime<App>, key: Key) {
        rt.key(KeyEvent { key, mods: Mods { cmd: true, ..Mods::default() } });
        rt.frame(1.0 / 60.0);
    }

    #[test]
    fn in_note_enter_on_a_paper_empties_the_field_for_the_note() {
        let mut rt = runtime();
        command(&mut rt, Key::Command('4'));
        assert_eq!(rt.state.panel.mode, mode::Mode::Note);
        rt.paste("graph");
        rt.frame(1.0 / 60.0);
        press(&mut rt, Key::Enter);
        assert_eq!(rt.state.query.text, "", "the field now takes the note");
        rt.paste("Compare heads");
        rt.frame(1.0 / 60.0);
        press(&mut rt, Key::Enter);
        let note = Effect::SaveNote { seq: 1, paper_id: "b".into(), body: "Compare heads".into() };
        assert_eq!(rt.state.sent, vec![note]);
    }

    #[test]
    fn tab_and_command_digits_move_along_the_mode_bar_and_a_pill_click_picks_one() {
        let mut rt = runtime();
        assert!(rt.find("mode-3").is_some(), "a pill per mode");
        press(&mut rt, Key::Tab);
        assert_eq!(rt.state.panel.mode, mode::Mode::Cite);
        command(&mut rt, Key::Command('5'));
        assert_eq!(rt.state.panel.mode, mode::Mode::Novelty);
        let (x, y) = rt.find("mode-0").expect("the Find pill");
        rt.pointer_move(x, y);
        rt.pointer_down(x, y);
        rt.pointer_up(x, y);
        rt.frame(1.0 / 60.0);
        assert_eq!(rt.state.panel.mode, mode::Mode::Find);
    }

    #[test]
    fn command_enter_in_cite_asks_for_bibtex() {
        let mut rt = runtime();
        press(&mut rt, Key::Tab);
        command(&mut rt, Key::Enter);
        assert!(matches!(rt.state.sent.as_slice(), [Effect::Cite { format: api::Format::Bibtex, .. }]), "{:?}", rt.state.sent);
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
