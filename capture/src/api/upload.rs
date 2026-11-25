//! A PDF from disk, uploaded as PaperLab's own Upload does (`POST /api/papers`, multipart); PaperLab then reads it.

use std::path::Path;

use super::{Api, ApiError, ok};
use crate::library::Paper;

const BOUNDARY: &str = "paperlab-capture-7f3a9c1e";

impl Api {
    pub fn upload(&self, path: &Path) -> Result<Paper, ApiError> {
        let name = file_name(path);
        let bytes = std::fs::read(path).map_err(|e| ApiError::Said(format!("Couldn't read “{name}” ({e}).")))?;
        let request = self.agent.post(format!("{}/api/papers", self.base))
            .header("content-type", format!("multipart/form-data; boundary={BOUNDARY}"));
        let (status, body) = self.send(request.send(&multipart(&name, &bytes)[..]))?;
        ok(status, body)
    }
}

fn file_name(path: &Path) -> String {
    path.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_else(|| "untitled.pdf".into())
}

/// One `file` part. The name's quotes and line breaks are dropped so it can't end its header early.
pub(super) fn multipart(name: &str, bytes: &[u8]) -> Vec<u8> {
    let name: String = name.chars().filter(|c| !matches!(c, '"' | '\r' | '\n')).collect();
    let head = format!(
        "--{BOUNDARY}\r\ncontent-disposition: form-data; name=\"file\"; filename=\"{name}\"\r\ncontent-type: application/pdf\r\n\r\n"
    );
    [head.as_bytes(), bytes, format!("\r\n--{BOUNDARY}--\r\n").as_bytes()].concat()
}
