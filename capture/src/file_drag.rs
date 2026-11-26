//! A file being dragged from another app, seen from outside. Rune takes file drops on windows but not on overlays,
//! and the floating paper is an overlay: so it watches for a drag instead (the mouse button held, the system's drag
//! pasteboard changed since the press, files on it) and, once that drag is over the page, opens the panel (a window)
//! under the pointer for the drop to land on.

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
}

#[cfg(target_os = "macos")]
pub use mac::{carries_files, sense};

#[cfg(not(target_os = "macos"))]
pub fn sense() -> Sense {
    Sense::default() // the floating paper is macOS only
}

#[cfg(not(target_os = "macos"))]
pub fn carries_files() -> bool {
    false
}
