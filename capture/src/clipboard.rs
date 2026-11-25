//! The system clipboard, through macOS's own `pbcopy` and `pbpaste`.

use std::io::{Read, Write};
use std::process::{Command, Stdio};

pub fn copy(text: &str) -> std::io::Result<()> {
    let mut child = Command::new("pbcopy").stdin(Stdio::piped()).spawn()?;
    child.stdin.take().expect("stdin was piped").write_all(text.as_bytes())?;
    let status = child.wait()?;
    if status.success() { Ok(()) } else { Err(std::io::Error::other(format!("pbcopy exited with {status}"))) }
}

/// Past this, the clipboard holds prose or data, never a paper's identifier: `paste` reads no further.
const PASTE_LIMIT: u64 = 2048;

/// The clipboard's text when it is short (PASTE_LIMIT), or None: empty, longer, or unreadable.
pub fn paste() -> Option<String> {
    let mut child = Command::new("pbpaste").stdout(Stdio::piped()).spawn().ok()?;
    let mut bytes = Vec::new();
    let read = child.stdout.take()?.take(PASTE_LIMIT + 1).read_to_end(&mut bytes);
    let _ = child.kill(); // a long clipboard is still being written: stop it
    let _ = child.wait();
    read.ok()?;
    (!bytes.is_empty() && bytes.len() as u64 <= PASTE_LIMIT).then(|| String::from_utf8_lossy(&bytes).into_owned())
}
