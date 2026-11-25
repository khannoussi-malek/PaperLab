//! The floating paper's tests (float.rs): its decisions, read from the `Act`s it returns, and a few through Rune's
//! test runtime.

use super::*;

/// A laptop, and a bigger monitor to its right with its top a little higher (as in place.rs).
const LAPTOP: Rect = [0.0, 0.0, 1440.0, 900.0];
const MONITOR: Rect = [1440.0, -200.0, 2560.0, 1440.0];
/// Big enough for the overlay at its biggest (the page, its glow and every bubble).
const VIEWPORT: (f32, f32) = (800.0, 800.0);

thread_local! {
    /// What the fake mouse and drag pasteboard say (`sensed`).
    static SENSE: std::cell::Cell<crate::file_drag::Sense> = std::cell::Cell::default();
}

fn sensed() -> crate::file_drag::Sense {
    SENSE.with(|s| s.get())
}

fn set_sense(button: bool, count: isize) {
    SENSE.with(|s| s.set(crate::file_drag::Sense { button, count }));
}

/// A floating paper with nothing to tell (its `Act`s are the answer) and an empty clipboard, its clock at `t`.
fn paper_at(t: f64) -> Float {
    let mut f = Float::new(None, vec![LAPTOP]);
    (f.paste, f.read_displays, f.read_pointer) = (|| None, || vec![], || None);
    (f.sense, f.carries_files, f.drag_link) = (sensed, || true, || None);
    f.tick(t);
    f
}

#[test]
fn a_copied_doi_adds_a_first_bubble_that_looks_it_up_in_find() {
    let mut f = paper_at(10.0);
    f.paste = || Some("  https://doi.org/10.48550/arXiv.1706.03762 \n".into());
    f.click();
    assert_eq!(f.items[0], Bubble::Copied(Input::Doi("10.48550/arXiv.1706.03762".into())));
    assert_eq!(f.items.len(), bubbles::MAX);
    let acts = f.pick(f.items[0].clone());
    let query = Some("10.48550/arXiv.1706.03762".to_owned());
    assert_eq!(acts, vec![Act::Show { at: f.panel_at(), mode: Some(Mode::Find), query }]);
}

#[test]
fn an_arxiv_link_counts_and_a_changed_clipboard_pops_its_bubbles_from_the_page() {
    let mut f = paper_at(10.0);
    f.paste = || Some("https://arxiv.org/abs/1706.03762".into());
    f.click();
    assert_eq!(f.items[0], Bubble::Copied(Input::Arxiv("1706.03762".into())));
    f.tick(11.0);
    f.click(); // the six start folding from where they are
    f.paste = || None;
    f.tick(11.02);
    f.click(); // the modes alone, reopened mid-fold
    assert_eq!(f.items[0], Bubble::Mode(Mode::Find));
    assert_eq!(f.bubbles_out()[0], 0.0, "Find pops from the page, not from where the copied bubble was");
}

#[test]
fn copied_prose_a_web_page_or_nothing_adds_no_bubble() {
    for paste in [(|| None) as fn() -> Option<String>, || Some("a sentence about attention".into()),
        || Some("https://news.example.com/today".into())] {
        let mut f = paper_at(10.0);
        f.paste = paste;
        f.click();
        assert_eq!(f.items, bubbles::menu(None));
    }
}

#[test]
fn a_click_brings_the_bubbles_out_and_a_second_folds_them() {
    let mut f = paper_at(10.0);
    assert_eq!(f.click(), vec![], "no panel yet: the bubbles are the menu");
    assert_eq!(f.focus, Focus::Menu, "bubbles out, page big and still");
    f.tick(11.0);
    assert_eq!(f.click(), vec![]);
    assert_eq!(f.focus, Focus::Floating, "folded, floating again");
}

#[test]
fn picking_a_bubble_opens_the_panel_beside_the_page_in_that_mode() {
    let mut f = paper_at(10.0);
    f.click();
    let acts = f.pick(Bubble::Mode(Mode::Ask));
    assert_eq!(acts, vec![Act::Show { at: f.panel_at(), mode: Some(Mode::Ask), query: None }]);
    assert_eq!(f.focus, Focus::Panel, "the bubbles fold; the page stays still beside its panel");
    assert_eq!(f.click(), vec![Act::ClosePanel], "a click on the page closes the panel");
}

#[test]
fn the_click_that_closed_the_panel_brings_nothing_out() {
    let mut f = paper_at(10.0);
    f.click();
    f.pick(Bubble::Mode(Mode::Find));
    f.panel_closed(); // focus left the panel for the page
    assert_eq!(f.click(), vec![]);
    assert_eq!(f.focus, Focus::Floating);
    f.tick(10.5);
    f.click();
    assert_eq!(f.focus, Focus::Menu, "a later click does");
}

#[test]
fn the_bubbles_fold_by_themselves_unless_the_pointer_is_on_one() {
    let mut f = paper_at(10.0);
    f.click();
    f.hover(true);
    f.tick(10.0 + 3.0 * MENU_IDLE);
    assert_eq!(f.focus, Focus::Menu, "pointed at: they stay");
    f.hover(false);
    f.tick(10.0 + 4.0 * MENU_IDLE - 0.1);
    assert_eq!(f.focus, Focus::Menu, "not yet");
    f.tick(10.0 + 4.0 * MENU_IDLE);
    assert_eq!(f.focus, Focus::Floating, "left alone: folded, floating again");
}

#[test]
fn the_bubbles_are_drawn_only_once_out_and_a_press_on_one_picks_it() {
    use rune::{Env, Runtime};
    let mut rt = Runtime::new(paper_at(10.0), view, VIEWPORT, Env { system_dark: false, scale: 2.0 });
    rt.frame(0.0);
    assert!(rt.find("bubble-0").is_none(), "folded: nothing drawn, nothing to catch a click");
    rt.update(|s, _| {
        s.click();
        s.tick(11.0);
    });
    rt.frame(1.0 / 60.0);
    let (x, y) = rt.find("bubble-2").expect("Ask is out");
    rt.pointer_down(x, y);
    rt.pointer_up(x, y);
    rt.frame(1.0 / 60.0);
    assert_eq!(rt.state.focus, Focus::Panel, "picked: folded, the panel would open");
}

#[test]
fn a_quick_second_click_folds_the_bubbles_from_where_they_are() {
    let mut f = paper_at(10.0);
    f.click();
    f.tick(10.08); // the first bubble partly out, the last not started
    let then = f.bubbles_out();
    assert!(then[0] > 0.0 && then[0] < 1.0 && then[4] == 0.0, "{then:?}");
    f.click();
    assert_eq!(f.bubbles_out(), then, "the fold starts where the pop was: nothing jumps");
    f.tick(10.2); // the top bubble folds last
    assert!(f.bubbles_out()[0] < then[0] && f.bubbles_out()[4] == 0.0);
}

#[test]
fn dragging_the_page_keeps_the_bubbles_out() {
    use rune::{Env, Runtime};
    let mut rt = Runtime::new(paper_at(10.0), view, VIEWPORT, Env { system_dark: false, scale: 2.0 });
    rt.update(|s, _| { s.click(); });
    rt.frame(0.0);
    let (x, y) = rt.find("paper").expect("the page");
    rt.pointer_down(x, y);
    rt.update(|s, _| s.tick(10.0 + MENU_IDLE - 0.5));
    rt.pointer_move(x + 40.0, y);
    rt.frame(1.0 / 60.0);
    rt.update(|s, _| s.tick(10.0 + MENU_IDLE + 1.0));
    assert!(rt.state.dragging, "the drag is under way");
    assert_eq!(rt.state.focus, Focus::Menu, "being moved isn't being left alone");
}

#[test]
fn a_right_click_offers_open_paperlab_and_hide() {
    let mut f = paper_at(10.0);
    assert_eq!(f.right_click(), vec![]);
    assert_eq!((f.focus, &f.items), (Focus::Menu, &bubbles::paper_menu()));
    assert_eq!(f.pick(Bubble::OpenPaperLab), vec![Act::OpenPaperLab]);
    assert_eq!(f.focus, Focus::Floating, "PaperLab comes forward; the paper floats again");
    f.tick(11.0);
    f.click();
    assert_eq!(f.items, bubbles::menu(None), "a left click is back to the functions");
}

#[test]
fn a_right_click_mid_drag_does_nothing_and_a_hidden_paper_polls_once_a_second() {
    let mut f = paper_at(10.0);
    f.dragging = true;
    assert_eq!(f.right_click(), vec![]);
    assert_eq!(f.focus, Focus::Floating);
    f.dragging = false;
    f.right_click();
    f.pick(Bubble::Hide);
    let mut tx = Tx::default();
    assert!(!poll(&mut f, 20.0, &mut tx), "hidden: no frame to draw");
    assert_eq!(f.t, 20.0, "the clock still moves");
    f.unhide();
    assert!(poll(&mut f, 20.5, &mut Tx::default()), "back: frames again");
}

#[test]
fn hidden_for_an_hour_it_draws_nothing_until_then_or_until_the_shortcut() {
    use rune::{Env, Runtime};
    let mut rt = Runtime::new(paper_at(10.0), view, VIEWPORT, Env { system_dark: false, scale: 2.0 });
    rt.update(|s, _| {
        s.right_click();
        assert_eq!(s.pick(Bubble::Hide), vec![]);
    });
    rt.frame(1.0 / 60.0);
    assert!(rt.find("paper").is_none(), "nothing to see or click");
    rt.update(|s, _| s.tick(10.0 + HIDE_FOR - 1.0));
    rt.frame(1.0 / 60.0);
    assert!(rt.find("paper").is_none(), "not yet");
    rt.update(|s, _| s.tick(10.0 + HIDE_FOR));
    rt.frame(1.0 / 60.0);
    assert!(rt.find("paper").is_some(), "back after the hour");
    rt.update(|s, _| {
        s.right_click();
        s.pick(Bubble::Hide);
        s.unhide();
    });
    rt.frame(1.0 / 60.0);
    assert!(rt.find("paper").is_some(), "the shortcut brings it back at once");
}

#[test]
fn the_badge_pulses_once_when_the_inbox_grows_and_not_when_it_shrinks() {
    let mut f = paper_at(10.0);
    f.set_badge(2);
    f.tick(10.0 + PULSE_SECONDS / 2.0);
    assert!(f.badge_scale() > 1.3, "mid-pulse");
    f.tick(10.0 + PULSE_SECONDS);
    assert_eq!(f.badge_scale(), 1.0, "once");
    f.set_badge(1);
    f.tick(11.0 + PULSE_SECONDS / 2.0);
    assert_eq!((f.badge, f.badge_scale()), (1, 1.0), "one read: no pulse");
}

/// A paper whose pointer (AppKit, bottom-left) is on its page.
fn pointed_at() -> Float {
    let mut f = paper_at(10.0);
    f.page = (1300.0, 700.0);
    f.read_pointer = || Some((1305.0, 900.0 - 705.0));
    f
}

#[test]
fn a_file_dragged_over_the_page_opens_the_panel_under_the_pointer_once() {
    let mut f = pointed_at();
    set_sense(true, 5);
    assert_eq!(f.watch_drag(), vec![], "the button went down: nothing is dragged yet");
    set_sense(true, 6); // a drag started: the drag pasteboard changed
    let acts = f.watch_drag();
    let at = place::drop_spot((1305.0, 705.0), LAPTOP);
    assert_eq!(acts, vec![Act::Show { at, mode: Some(Mode::Find), query: None }, Act::Take(Event::DropOffered)]);
    assert_eq!(f.focus, Focus::Panel);
    assert_eq!(f.watch_drag(), vec![], "once per drag");
    set_sense(false, 6);
    assert_eq!(f.watch_drag(), vec![Act::Take(Event::DragEnded)], "the drag ended: the panel is told");
    assert_eq!(f.watch_drag(), vec![]);
}

#[test]
fn a_held_button_text_drag_or_a_drag_elsewhere_opens_nothing() {
    let mut f = pointed_at();
    set_sense(true, 5);
    f.watch_drag();
    assert_eq!(f.watch_drag(), vec![], "button held, no drag (a selection): nothing");
    set_sense(true, 6);
    f.read_pointer = || Some((200.0, 900.0 - 200.0));
    assert_eq!(f.watch_drag(), vec![], "files, but far from the page: nothing yet");
    f.read_pointer = || Some((1300.0, 900.0 - 700.0));
    assert_eq!(f.watch_drag().len(), 2, "carried over the page: the panel opens");
    set_sense(false, 6);
    assert_eq!(f.watch_drag(), vec![Act::Take(Event::DragEnded)]);
    let mut text = pointed_at();
    set_sense(true, 9);
    text.watch_drag();
    set_sense(true, 10);
    text.carries_files = || false;
    assert_eq!(text.watch_drag(), vec![], "a drag of text: nothing");
    text.carries_files = || panic!("decided: the pasteboard isn't read again this drag");
    assert_eq!(text.watch_drag(), vec![]);
    set_sense(false, 10);
    assert_eq!(text.watch_drag(), vec![], "and its end tells no one");
    let mut own = pointed_at();
    set_sense(true, 7);
    own.watch_drag();
    own.dragging = true; // the page itself being moved
    set_sense(true, 8);
    assert_eq!(own.watch_drag(), vec![], "its own drag isn't a file drop");
}

/// A paper just let go against the laptop's right edge, the pointer gone, its clock at `t`.
fn left_at_the_right_edge(t: f64) -> Float {
    let mut f = paper_at(t);
    f.page = place::keep_page((9000.0, 400.0), (BIG.0 / 2.0, BIG.1 / 2.0), &f.displays);
    f.dragging = true;
    assert_eq!(f.release(false), vec![], "a drag's end isn't a click");
    f
}

/// How much of the drawn page is on the laptop, across.
fn showing(f: &Float) -> f32 {
    let [x, _, w, _] = f.drawn_rect(SMALL);
    (x + w).min(1440.0) - x.max(0.0)
}

#[test]
fn let_go_against_an_edge_it_tucks_in_once_the_pointer_has_left_leaving_a_tab() {
    let mut f = left_at_the_right_edge(10.0);
    assert_eq!(f.tuck.edge(), Some(Edge::Right));
    f.tick(10.0 + tuck::DELAY / 2.0);
    assert_eq!(showing(&f), SMALL.0, "a moment first: all of it still showing");
    f.tick(10.0 + tuck::DELAY); // a frame each refresh: the slide starts as the moment is up
    f.tick(10.0 + tuck::DELAY + tuck::SECONDS / 2.0);
    assert!(showing(&f) < SMALL.0 && showing(&f) > tuck::TAB, "sliding in: {}", showing(&f));
    f.tick(10.0 + tuck::DELAY + tuck::SECONDS + 0.1);
    assert!((showing(&f) - tuck::TAB).abs() < 0.01, "tucked: just the tab, {}", showing(&f));
    assert!(f.placed[0] + f.placed[2] <= 1440.0, "its overlay stays on the screen");
}

#[test]
fn pointing_at_the_tab_or_opening_the_bubbles_slides_it_out_with_a_little_overshoot() {
    let mut f = left_at_the_right_edge(10.0);
    f.tick(10.0 + tuck::DELAY);
    f.tick(12.0);
    f.read_pointer = || Some((1436.0, 900.0 - 400.0)); // on the tab
    f.tick(12.1);
    f.tick(12.1 + tuck::SECONDS * 0.6);
    assert!(f.tuck.amount(f.t) < 0.0, "past out, a touch: the bounce ({})", f.tuck.amount(f.t));
    f.tick(12.1 + tuck::SECONDS + 0.01);
    assert_eq!(showing(&f), SMALL.0, "all of it out");
    f.read_pointer = || None; // the pointer left
    f.tick(13.0);
    f.tick(13.0 + tuck::DELAY);
    f.tick(13.0 + tuck::DELAY + tuck::SECONDS);
    assert!((showing(&f) - tuck::TAB).abs() < 0.01, "and back in");
    f.click();
    f.tick(14.0);
    f.tick(14.0 + tuck::SECONDS + 0.01);
    assert_eq!((f.focus, showing(&f)), (Focus::Menu, SMALL.0), "bubbles out: so is the page");
}

#[test]
fn dragged_away_from_the_edge_it_is_free_and_let_go_mid_screen_it_stays_out() {
    let mut f = left_at_the_right_edge(10.0);
    f.grab_page();
    f.drag_to((-400.0, 0.0));
    assert_eq!(f.tuck.edge(), None);
    f.release(false);
    assert_eq!(f.tuck.edge(), None, "mid-screen: free");
    f.tick(20.0);
    assert_eq!(f.drawn(), f.page);
}

#[test]
fn it_starts_bottom_right_of_the_main_display_in_a_glow_sized_overlay() {
    let f = Float::new(None, vec![MONITOR, LAPTOP]);
    let [x, y, w, h] = f.page_rect(BIG);
    assert!(x > 1000.0 && x + w < 1440.0 && y + h < 900.0, "on the laptop, bottom right: {x} {y}");
    assert_eq!((f.placed[2], f.placed[3]), (2.0 * HALO, 2.0 * HALO), "folded: just the glow");
}

#[test]
fn a_drag_carries_the_page_onto_the_other_display_and_right_to_its_edge() {
    let mut f = paper_at(10.0);
    f.displays = vec![LAPTOP, MONITOR];
    let grab = f.page;
    f.grab_page();
    f.drag_to((600.0, -300.0));
    assert_eq!(place::display_of(f.page, &f.displays), MONITOR, "across onto the monitor");
    assert_eq!(f.page, (grab.0 + 600.0, grab.1 - 300.0), "where the pointer took it");
    f.drag_to((9000.0, 0.0));
    let [x, _, w, _] = f.page_rect(BIG);
    assert_eq!(x + w, MONITOR[0] + MONITOR[2], "right up to the monitor's edge");
    let [ox, _, ow, _] = f.placed;
    assert_eq!(ox + ow, MONITOR[0] + MONITOR[2], "and its overlay stays on the monitor, cut at the edge");
    let (px, _) = f.panel_at();
    assert!(px >= MONITOR[0] && px + crate::view::WIDTH <= MONITOR[0] + MONITOR[2], "its panel opens there too");
}

#[test]
fn a_drag_onto_a_monitor_on_the_left_follows_appkits_pointer_not_runes_travel() {
    /// A 1x monitor left of the laptop, its top level with the laptop's.
    const LEFT: Rect = [-1920.0, 0.0, 1920.0, 1080.0];
    let mut f = paper_at(10.0);
    f.displays = vec![LAPTOP, LEFT];
    f.page = (1300.0, 700.0);
    f.read_pointer = || Some((1300.0, 900.0 - 700.0)); // AppKit: bottom-left origin, on the page
    f.grab_page();
    assert_eq!(f.pressed_at, Some((1300.0, 200.0)), "as AppKit gave it");
    f.read_pointer = || Some((-600.0, 900.0 - 500.0)); // well onto the left monitor
    let travel = f.travel((-40.0, 3.0)); // Rune's travel, thrown off by the change of scale
    assert_eq!(travel, (-1900.0, -200.0));
    f.drag_to(travel);
    assert_eq!(f.page, (-600.0, 500.0), "on the left monitor, under the pointer");
    assert_eq!(place::display_of(f.page, &f.displays), LEFT);
    assert!(f.placed[0] < 0.0, "its overlay went with it: {:?}", f.placed);
    f.drag_to((-9000.0, 0.0));
    assert_eq!(f.page_rect(BIG)[0], -1920.0, "and right to its left edge");
}

#[test]
fn without_appkits_pointer_runes_travel_is_used() {
    let mut f = paper_at(10.0);
    f.grab_page();
    assert_eq!(f.travel((12.0, -5.0)), (12.0, -5.0));
}

#[test]
fn a_monitor_unplugged_brings_the_page_back_to_one_that_is_there() {
    let mut f = paper_at(10.0);
    f.displays = vec![LAPTOP, MONITOR];
    f.page = (3000.0, 500.0);
    f.read_displays = || vec![LAPTOP];
    f.tick(10.0 + DISPLAYS_EVERY);
    assert_eq!(place::display_of(f.page, &[LAPTOP]), LAPTOP);
    let [x, _, w, _] = f.page_rect(BIG);
    assert_eq!(x + w, 1440.0, "at the laptop's edge, nearest where it was");
}

#[test]
fn the_overlay_grows_to_hold_the_bubbles_and_shrinks_once_they_have_folded() {
    let mut f = paper_at(10.0);
    let small = f.placed;
    f.click();
    f.tick(11.0);
    let [x, y, w, h] = f.placed;
    assert!(w > small[2] && h > small[3], "bigger: {:?}", f.placed);
    for (sx, sy) in f.spots() {
        assert!(sx >= x && sy >= y && sx + PILL.0 <= x + w && sy + PILL.1 <= y + h, "every bubble inside");
    }
    f.click();
    f.tick(11.05);
    assert!(f.placed[2] > small[2], "still folding: still big");
    f.tick(12.0);
    assert_eq!(f.placed, small, "folded: back to the glow");
}

#[test]
fn grabbed_by_its_tab_a_tucked_page_moves_with_the_pointer_without_a_jump() {
    let mut f = left_at_the_right_edge(10.0);
    f.tick(10.0 + tuck::DELAY);
    f.tick(10.0 + tuck::DELAY + tuck::SECONDS);
    let at = f.drawn();
    f.grab_page();
    f.drag_to((-200.0, 0.0));
    assert_eq!(f.tuck.edge(), None, "taken off its side");
    assert_eq!(f.page, (at.0 - 200.0, at.1), "from where it was drawn, by as much as the pointer went");
}

#[test]
fn a_display_change_frees_a_tucked_page() {
    let mut f = left_at_the_right_edge(10.0);
    f.read_displays = || vec![[0.0, 0.0, 1280.0, 800.0]];
    f.tick(10.0 + DISPLAYS_EVERY);
    assert_eq!(f.tuck.edge(), None);
}

#[test]
fn a_copied_publisher_link_gets_its_bubble_and_any_other_page_does_not() {
    let mut f = paper_at(10.0);
    f.paste = || Some("https://www.nature.com/articles/s41586-021-03819-2".into());
    f.click();
    let link = Input::Link("https://www.nature.com/articles/s41586-021-03819-2".into());
    assert_eq!(f.items[0], Bubble::Copied(link));
    f.tick(11.0);
    f.click();
    f.paste = || Some("https://news.example.com/today".into());
    f.tick(12.0);
    f.click();
    assert_eq!(f.items, bubbles::menu(None));
}

#[test]
fn a_link_dragged_from_a_browser_lights_the_page_and_let_go_on_it_is_looked_up() {
    let mut f = pointed_at();
    (f.carries_files, f.drag_link) = (|| false, || Some("https://www.nature.com/articles/x".into()));
    set_sense(true, 5);
    f.watch_drag();
    set_sense(true, 6);
    assert_eq!(f.watch_drag(), vec![], "nothing opens while it's held");
    assert!(f.link_over(), "the page lights up as its target");
    set_sense(false, 6);
    let query = Some("https://www.nature.com/articles/x".to_owned());
    assert_eq!(f.watch_drag(), vec![Act::Show { at: f.panel_at(), mode: Some(Mode::Find), query }]);
    assert_eq!((f.focus, f.link_over()), (Focus::Panel, false));
}

#[test]
fn a_link_carried_away_from_the_page_and_let_go_elsewhere_does_nothing() {
    let mut f = pointed_at();
    (f.carries_files, f.drag_link) = (|| false, || Some("https://example.org/paper".into()));
    set_sense(true, 5);
    f.watch_drag();
    set_sense(true, 6);
    f.watch_drag();
    f.read_pointer = || Some((200.0, 900.0 - 200.0)); // carried off the page
    f.watch_drag();
    assert!(!f.link_over(), "off the page: no longer lit");
    set_sense(false, 6);
    assert_eq!(f.watch_drag(), vec![]);
}

#[test]
fn a_drag_with_neither_files_nor_a_link_does_nothing() {
    let mut f = pointed_at();
    (f.carries_files, f.drag_link) = (|| false, || None);
    set_sense(true, 5);
    f.watch_drag();
    set_sense(true, 6);
    assert_eq!(f.watch_drag(), vec![]);
    set_sense(false, 6);
    assert_eq!(f.watch_drag(), vec![]);
}

#[test]
fn a_link_let_go_just_off_the_page_isnt_taken_even_if_it_was_over_it_a_frame_ago() {
    let mut f = pointed_at();
    (f.carries_files, f.drag_link) = (|| false, || Some("https://example.org/paper".into()));
    set_sense(true, 5);
    f.watch_drag();
    set_sense(true, 6);
    f.watch_drag();
    assert!(f.link_over());
    f.read_pointer = || Some((200.0, 900.0 - 200.0)); // moved off and let go in the same frame
    set_sense(false, 6);
    assert_eq!(f.watch_drag(), vec![]);
}
