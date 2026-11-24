//! PaperLab's own icon, for the panel's header: a 128 px copy of the app icon, decoded once at start.

use rune::Pixels;

const PNG: &[u8] = include_bytes!("../assets/paperlab-icon.png");

/// The icon as Rune pixels; empty (nothing drawn) if it can't be decoded, so the panel still opens.
pub fn pixels() -> Pixels {
    let pixels = Pixels::new();
    if let Some((width, height, rgba)) = rgba(PNG) {
        pixels.set(width, height, rgba);
    }
    pixels
}

/// The PNG's width, height and 8-bit RGBA bytes; None for anything but an RGBA image.
fn rgba(png_bytes: &[u8]) -> Option<(u32, u32, Vec<u8>)> {
    let mut decoder = png::Decoder::new(std::io::Cursor::new(png_bytes));
    decoder.set_transformations(png::Transformations::normalize_to_color8());
    let mut reader = decoder.read_info().ok()?;
    let mut buf = vec![0; reader.output_buffer_size()?];
    let frame = reader.next_frame(&mut buf).ok()?;
    if frame.color_type != png::ColorType::Rgba {
        return None;
    }
    buf.truncate(frame.buffer_size());
    Some((frame.width, frame.height, buf))
}

#[cfg(test)]
mod tests {
    #[test]
    fn the_bundled_icon_decodes_to_128_px_rgba() {
        let (width, height, rgba) = super::rgba(super::PNG).expect("the bundled icon decodes");
        assert_eq!((width, height, rgba.len()), (128, 128, 128 * 128 * 4));
    }
}
