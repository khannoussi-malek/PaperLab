//! The displays as macOS has them now, in global points (see place.rs). Rune gives the list once, at start; a monitor
//! plugged in or out later only shows up here, so the floating paper asks again every few seconds.

use crate::place::Rect;

/// The displays' bounds, top-left origin; empty off the main thread or off macOS (then the list from start stays).
#[cfg(target_os = "macos")]
pub fn read() -> Vec<Rect> {
    use objc2::MainThreadMarker;
    use objc2_app_kit::NSScreen;
    let Some(mtm) = MainThreadMarker::new() else {
        static SAID: std::sync::Once = std::sync::Once::new();
        SAID.call_once(|| {
            eprintln!("paperlab-capture: displays read off the main thread; a monitor change needs a restart");
        });
        return vec![];
    };
    let frames: Vec<[f64; 4]> = NSScreen::screens(mtm).iter()
        .map(|s| s.frame())
        .map(|f| [f.origin.x, f.origin.y, f.size.width, f.size.height])
        .collect();
    from_appkit(&frames)
}

/// The pointer, as AppKit has it: global points from the main display's bottom-left, y up. Points are the same size on
/// every display, so the distance between two readings is the pointer's real travel, wherever it went.
#[cfg(target_os = "macos")]
pub fn pointer() -> Option<(f64, f64)> {
    let at = objc2_app_kit::NSEvent::mouseLocation();
    Some((at.x, at.y))
}

#[cfg(not(target_os = "macos"))]
pub fn pointer() -> Option<(f64, f64)> {
    None // Rune's own drag travel is used instead
}

#[cfg(not(target_os = "macos"))]
pub fn read() -> Vec<Rect> {
    vec![] // the floating paper is macOS only (Settings → Desktop app)
}

/// AppKit's screen frames (bottom-left origin, y up, the first screen the main one) as global top-left rects.
#[cfg_attr(not(target_os = "macos"), allow(dead_code))]
fn from_appkit(frames: &[[f64; 4]]) -> Vec<Rect> {
    let Some(main_height) = frames.first().map(|f| f[3]) else { return vec![] };
    frames.iter().filter(|f| f[2] > 0.0 && f[3] > 0.0)
        .map(|&[x, y, w, h]| [x as f32, (main_height - y - h) as f32, w as f32, h as f32])
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn appkit_frames_flip_to_top_left_with_the_main_screen_at_the_origin() {
        // a laptop, and a monitor to its right whose bottom sits 300 pt below the laptop's
        let frames = [[0.0, 0.0, 1440.0, 900.0], [1440.0, -300.0, 2560.0, 1440.0]];
        assert_eq!(from_appkit(&frames), vec![[0.0, 0.0, 1440.0, 900.0], [1440.0, -240.0, 2560.0, 1440.0]]);
        assert_eq!(from_appkit(&[]), Vec::<Rect>::new());
    }
}
