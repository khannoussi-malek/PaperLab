//! The system clipboard, through macOS's own `pbcopy` and `pbpaste`.

use std::io::Write;
use std::process::{Command, Stdio};

pub fn copy(text: &str) -> std::io::Result<()> {
    let mut child = Command::new("pbcopy").stdin(Stdio::piped()).spawn()?;
    child.stdin.take().expect("stdin was piped").write_all(text.as_bytes())?;
    let status = child.wait()?;
    if status.success() { Ok(()) } else { Err(std::io::Error::other(format!("pbcopy exited with {status}"))) }
}

/// The clipboard's text, or None when it holds none or can't be read.
pub fn paste() -> Option<String> {
    let out = Command::new("pbpaste").output().ok()?;
    out.status.success().then(|| String::from_utf8_lossy(&out.stdout).into_owned()).filter(|text| !text.is_empty())
}
