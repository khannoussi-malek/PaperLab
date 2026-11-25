//! A file or a link being dragged from another app, seen from outside. Rune takes file drops on windows but not on
//! overlays, and the floating paper is an overlay: so it watches for a drag instead (the mouse button held, the
//! system's drag pasteboard changed since the press) and reads what it carries. Files: once over the page, the panel (a
//! window) opens under the pointer for the drop to land on. A link: read from the drag itself when let go on the page.

/// The mouse button, and the drag pasteboard's change count (it moves when a drag starts).
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Sense {
    pub button: bool,
    pub count: isize,
}

#[cfg(target_os = "macos")]
mod mac {
    use objc2::rc::Retained;
    use objc2_app_kit::{NSEvent, NSPasteboard};
    use objc2_foundation::NSString;

    /// The value of AppKit's `NSPasteboardNameDrag` (the constant itself is an extern static, which would take
    /// unsafe code; this crate has none).
    const DRAG: &str = "Apple CFPasteboard drag";
    /// What a drag of files from Finder (and most apps) carries.
    const FILE_TYPES: [&str; 2] = ["public.file-url", "NSFilenamesPboardType"];

    fn board() -> Retained<NSPasteboard> {
        NSPasteboard::pasteboardWithName(&NSString::from_str(DRAG))
    }

    pub fn sense() -> super::Sense {
        super::Sense { button: NSEvent::pressedMouseButtons() & 1 != 0, count: board().changeCount() }
    }

    pub fn carries_files() -> bool {
        let Some(types) = board().types() else { return false };
        types.iter().any(|t| FILE_TYPES.iter().any(|f| t.to_string() == *f))
    }

    /// The web link the drag carries (a link or the address dragged from a browser), if any: one http(s) URL, not a
    /// paragraph that happens to start with one.
    pub fn link() -> Option<String> {
        let board = board();
        ["public.url", "public.utf8-plain-text"].into_iter()
            .filter_map(|kind| board.stringForType(&NSString::from_str(kind)))
            .map(|text| text.to_string().trim().to_owned())
            .find(|text| super::is_web_link(text))
    }
}

#[cfg(target_os = "macos")]
pub use mac::{carries_files, link, sense};

/// One http(s) URL and nothing else.
#[cfg_attr(not(target_os = "macos"), allow(dead_code))]
fn is_web_link(text: &str) -> bool {
    let lower = text.to_ascii_lowercase();
    (lower.starts_with("https://") || lower.starts_with("http://")) && !text.contains(char::is_whitespace)
}

#[cfg(test)]
mod tests {
    #[test]
    fn a_web_link_is_one_url_in_any_case_and_not_a_paragraph() {
        assert!(super::is_web_link("HTTPS://www.nature.com/articles/x"));
        assert!(!super::is_web_link("https://example.org/a and then some words"));
        assert!(!super::is_web_link("ftp://example.org/x"));
    }
}

#[cfg(not(target_os = "macos"))]
pub fn sense() -> Sense {
    Sense::default() // the floating paper is macOS only
}

#[cfg(not(target_os = "macos"))]
pub fn carries_files() -> bool {
    false
}

#[cfg(not(target_os = "macos"))]
pub fn link() -> Option<String> {
    None
}
