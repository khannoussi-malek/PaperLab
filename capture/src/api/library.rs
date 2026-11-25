//! The library: every paper as a picker lists it, and one paper's status.

use super::{Api, ApiError, ok};
use crate::library::Paper;

impl Api {
    pub fn papers(&self) -> Result<Vec<Paper>, ApiError> {
        let (status, body) = self.send(self.agent.get(&format!("{}/api/papers/brief", self.base)).call())?;
        ok(status, body)
    }

    pub fn paper(&self, id: &str) -> Result<Paper, ApiError> {
        let (status, body) = self.send(self.agent.get(&format!("{}/api/papers/{id}", self.base)).call())?;
        ok(status, body)
    }
}
