//! A PDF from disk, uploaded as PaperLab's own Upload does (`POST /api/papers`, multipart); PaperLab then reads it.

use std::path::Path;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use super::{Api, ApiError, ok};
use crate::library::Paper;

/// Bigger than any paper; the whole file is held in memory while it goes up.
const MAX_BYTES: u64 = 200 << 20;
/// A big PDF over a slow disk: well past the client's usual minute. A retry after a timeout could add it twice.
const UPLOAD_TIMEOUT: Duration = Duration::from_secs(600);

impl Api {
    /// A paper from a link to its PDF: PaperLab downloads it (POST /api/papers/from-link), or answers with its copy.
    pub fn add_link(&self, link: &str) -> Result<Paper, ApiError> {
        let url = format!("{}/api/papers/from-link", self.base);
        let request = self.agent.post(&url).config().timeout_global(Some(UPLOAD_TIMEOUT)).build();
        let (status, body) = self.send(request.send_json(&serde_json::json!({ "link": link })))?;
        ok(status, body)
    }

    pub fn upload(&self, path: &Path) -> Result<Paper, ApiError> {
        let name = file_name(path);
        let unreadable = |e: std::io::Error| ApiError::Said(format!("Couldn't read “{name}” ({e})."));
        if std::fs::metadata(path).map_err(unreadable)?.len() > MAX_BYTES {
            return Err(ApiError::Said(format!("“{name}” is over 200 MB; add it from PaperLab instead.")));
        }
        let bytes = std::fs::read(path).map_err(unreadable)?;
        let boundary = boundary();
        let request = self.agent.post(format!("{}/api/papers", self.base))
            .header("content-type", format!("multipart/form-data; boundary={boundary}"))
            .config().timeout_global(Some(UPLOAD_TIMEOUT)).build();
        let (status, body) = self.send(request.send(&multipart(&boundary, &name, &bytes)[..]))?;
        ok(status, body)
    }
}

fn file_name(path: &Path) -> String {
    path.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_else(|| "untitled.pdf".into())
}

/// A boundary of its own per upload, so no PDF's bytes happen to contain it.
fn boundary() -> String {
    let nanos = SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_nanos()).unwrap_or_default();
    format!("paperlab-capture-{nanos:x}-{:x}", std::process::id())
}

/// One `file` part. The name's quotes and line breaks are dropped so it can't end its header early.
pub(super) fn multipart(boundary: &str, name: &str, bytes: &[u8]) -> Vec<u8> {
    let name: String = name.chars().filter(|c| !matches!(c, '"' | '\r' | '\n')).collect();
    let head = format!(
        "--{boundary}\r\ncontent-disposition: form-data; name=\"file\"; filename=\"{name}\"\r\ncontent-type: application/pdf\r\n\r\n"
    );
    [head.as_bytes(), bytes, format!("\r\n--{boundary}--\r\n").as_bytes()].concat()
}
