//! What the panel draws for a `Panel` state: the field, the mode bar, one line saying what's happening, and the rows
//! Enter acts on. Glass with a veil of the theme's card colour, so text keeps its contrast in light and dark mode.

mod answer;
mod rows;
mod status;

use rune::tok::{self, type_};
use rune::{Color, Cx, El, Key, KeyEvent, SystemMaterial, Tx, col, el, row, text, text_input};

use crate::App;
use crate::mode::{MODES, Mode};
use crate::panel::Event;

pub const WIDTH: f32 = 600.0;

/// The blue of PaperLab's icon: the selected row, the active mode, the light behind the icon.
pub(super) fn logo_blue() -> Color {
    rune::color::hex("#2664ee").expect("a valid colour")
}

/// The colours a view needs, for the system's appearance.
pub(super) struct Ink {
    pub dark: bool,
    pub text: Color,
    /// Secondary lines: the text colour at 72%, so they keep contrast on glass in both modes.
    pub muted: Color,
    pub separator: Color,
}

pub fn view(app: &App, cx: &mut Cx<App>) -> El {
    let dark = cx.system_dark();
    let t = tok::theme(dark);
    let ink = Ink { dark, text: t.text, muted: t.text.alpha(0.72), separator: t.separator };
    let p = &app.panel;
    let veil = t.card.alpha(if dark { 0.62 } else { 0.58 });
    let mut panel = col().key("panel").w(WIDTH).radius(14.0).clip_rounded(14.0).fill(t.card)
        // Liquid Glass over whatever is behind the window (the card colour where glass can't show).
        .system_material(SystemMaterial::Glass)
        .border(1.0, if dark { Color::WHITE.alpha(0.1) } else { t.separator })
        .child(el().key("veil").absolute(0.0, 0.0).w_full().h_full().fill(veil))
        .child(header(app, &ink))
        .child(mode_bar(p.mode, &ink));
    let status = status::line(p);
    let list = rows::list(p, &ink);
    if status.is_some() || list.is_some() {
        panel = panel.child(el().h(1.0).w_full().fill(ink.separator));
    }
    if let Some(line) = status {
        panel = panel.child(row().key("status").px(18.0).py(10.0)
            .child(text(line).font(type_::LABEL).color(ink.muted).w_full()));
    }
    if let Some(answer) = answer::block(p, &ink) {
        panel = panel.child(answer);
    }
    if let Some(list) = list {
        panel = panel.child(list);
    }
    col().w_full().child(panel)
}

/// PaperLab's icon with the logo's light behind it, and the field.
fn header(app: &App, ink: &Ink) -> El {
    let glow = logo_blue().alpha(if ink.dark { 0.34 } else { 0.2 });
    row().h(56.0).px(18.0).gap(12.0).center_y()
        .radial_gradient([31.0, 28.0], [220.0, 72.0], [(0.0, glow), (1.0, glow.alpha(0.0))])
        .child(el().size(26.0, 26.0).radius(6.0).pixels(&app.icon))
        .child(field(app, ink))
}

fn field(app: &App, ink: &Ink) -> El {
    text_input(&app.query, type_::BODY.lh(26.0)).key("query").single_line().grow(1.0)
        .color(ink.text).placeholder(app.panel.mode.placeholder(), ink.muted)
        .on_edit(|s: &mut App| &mut s.query)
        .on_input_change(|s: &mut App, _| { let q = s.query.text.clone(); s.dispatch(Event::Query(q)); })
        .on_input_key(|s: &mut App, ev: &KeyEvent, _: &mut Tx| key(s, ev))
        .on_submit(|s: &mut App, _| s.dispatch(Event::Submit))
}

/// The field's own keys: rows, modes, close. True when handled.
fn key(s: &mut App, ev: &KeyEvent) -> bool {
    let jump = (1..=MODES.len()).find(|&n| ev.is_command(char::from_digit(n as u32, 10).unwrap_or('0')));
    match (&ev.key, jump) {
        (_, Some(place)) => s.dispatch(Event::Mode(Mode::nth(place).unwrap_or_default())),
        (Key::Down, _) => s.dispatch(Event::Down),
        (Key::Up, _) => s.dispatch(Event::Up),
        (Key::Tab, _) => s.dispatch(Event::NextMode { forward: !ev.mods.shift }),
        (Key::Enter, _) if ev.mods.cmd => s.dispatch(Event::SubmitAlt),
        (Key::Escape, _) => s.close(),
        _ => return false,
    }
    true
}

/// One pill per mode; the active one in the logo's blue. Tab and ⌘1… move along it too.
fn mode_bar(active: Mode, ink: &Ink) -> El {
    let mut bar = row().key("modes").px(14.0).pb(10.0).gap(6.0).center_y();
    for (i, mode) in MODES.into_iter().enumerate() {
        let on = mode == active;
        bar = bar.child(row().key(format!("mode-{i}")).h(26.0).px(12.0).radius(13.0).center_y()
            .fill(if on { logo_blue() } else { Color::TRANSPARENT })
            .border(1.0, if on { Color::TRANSPARENT } else { ink.separator })
            .child(text(mode.label()).font(type_::LABEL).color(if on { Color::WHITE } else { ink.muted }))
            .on_press(move |s: &mut App| s.dispatch(Event::Mode(mode))));
    }
    bar.child(el().grow(1.0)).child(text("⇥ next").font(type_::LABEL).color(ink.muted.alpha(0.7)))
}
