use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExecutionPolicy {
    pub allowed_workspaces: Vec<PathBuf>,
    pub disallow_shell_patterns: Vec<String>,
}

impl Default for ExecutionPolicy {
    fn default() -> Self {
        Self {
            allowed_workspaces: vec![PathBuf::from("E:\\agent_system")],
            disallow_shell_patterns: vec![
                "rmdir /s".to_string(),
                "format ".to_string(),
                "del /f /s /q c:\\".to_string(),
            ],
        }
    }
}

impl ExecutionPolicy {
    pub fn validate_path(&self, target: &Path) -> bool {
        // Izinkan jika target berada di dalam allowed workspace atau relasi aman
        if self.allowed_workspaces.is_empty() {
            return true;
        }
        for ws in &self.allowed_workspaces {
            if target.starts_with(ws) || target.is_relative() {
                return true;
            }
        }
        false
    }

    pub fn validate_command(&self, cmd: &str) -> bool {
        let lower = cmd.to_lowercase();
        for blocked in &self.disallow_shell_patterns {
            if lower.contains(blocked) {
                return false;
            }
        }
        true
    }
}
