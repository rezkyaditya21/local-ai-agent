use crate::{Tool, ToolError};
use async_trait::async_trait;
use serde_json::{json, Value};
use std::path::Path;
use sysinfo::System;

// 1. System Info Tool
pub struct SystemInfoTool;

#[async_trait]
impl Tool for SystemInfoTool {
    fn name(&self) -> &'static str {
        "system.info"
    }

    fn description(&self) -> &'static str {
        "Ambil informasi telemetri sistem (CPU, RAM, OS, dan status proses)."
    }

    fn input_schema(&self) -> Value {
        json!({
            "type": "object",
            "properties": {}
        })
    }

    async fn execute(&self, _args: Value) -> Result<Value, ToolError> {
        let mut sys = System::new_all();
        sys.refresh_all();

        let total_mem = sys.total_memory() / (1024 * 1024);
        let used_mem = sys.used_memory() / (1024 * 1024);
        let cpus = sys.cpus().len();

        Ok(json!({
            "os": System::long_os_version().unwrap_or_default(),
            "cpu_cores": cpus,
            "total_ram_mb": total_mem,
            "used_ram_mb": used_mem,
            "free_ram_mb": total_mem.saturating_sub(used_mem),
        }))
    }
}

// 2. Filesystem Read Tool
pub struct FileReadTool;

#[async_trait]
impl Tool for FileReadTool {
    fn name(&self) -> &'static str {
        "filesystem.read"
    }

    fn description(&self) -> &'static str {
        "Membaca isi berkas teks dari path yang ditentukan."
    }

    fn input_schema(&self) -> Value {
        json!({
            "type": "object",
            "required": ["path"],
            "properties": {
                "path": { "type": "string", "description": "Lokasi berkas yang akan dibaca" }
            }
        })
    }

    async fn execute(&self, args: Value) -> Result<Value, ToolError> {
        let path_str = args.get("path")
            .and_then(|v| v.as_str())
            .ok_or_else(|| ToolError::InvalidArguments("Parameter 'path' wajib diisi".to_string()))?;

        let path = Path::new(path_str);
        if !path.exists() {
            return Err(ToolError::ExecutionFailed(format!("Berkas '{}' tidak ditemukan", path_str)));
        }

        let content = tokio::fs::read_to_string(path)
            .await
            .map_err(|e| ToolError::ExecutionFailed(e.to_string()))?;

        Ok(json!({
            "path": path_str,
            "content": content,
            "length": content.len()
        }))
    }
}

// 3. Filesystem Write Tool
pub struct FileWriteTool;

#[async_trait]
impl Tool for FileWriteTool {
    fn name(&self) -> &'static str {
        "filesystem.write"
    }

    fn description(&self) -> &'static str {
        "Menulis atau membuat berkas baru dengan isi teks tertentu."
    }

    fn input_schema(&self) -> Value {
        json!({
            "type": "object",
            "required": ["path", "content"],
            "properties": {
                "path": { "type": "string", "description": "Lokasi berkas yang akan ditulis" },
                "content": { "type": "string", "description": "Isi teks berkas" }
            }
        })
    }

    async fn execute(&self, args: Value) -> Result<Value, ToolError> {
        let path_str = args.get("path")
            .and_then(|v| v.as_str())
            .ok_or_else(|| ToolError::InvalidArguments("Parameter 'path' wajib diisi".to_string()))?;

        let content = args.get("content")
            .and_then(|v| v.as_str())
            .ok_or_else(|| ToolError::InvalidArguments("Parameter 'content' wajib diisi".to_string()))?;

        let path = Path::new(path_str);
        if let Some(parent) = path.parent() {
            tokio::fs::create_dir_all(parent)
                .await
                .map_err(|e| ToolError::ExecutionFailed(e.to_string()))?;
        }

        tokio::fs::write(path, content)
            .await
            .map_err(|e| ToolError::ExecutionFailed(e.to_string()))?;

        Ok(json!({
            "path": path_str,
            "status": "success",
            "bytes_written": content.len()
        }))
    }
}

// 4. Filesystem List Tool
pub struct FileListTool;

#[async_trait]
impl Tool for FileListTool {
    fn name(&self) -> &'static str {
        "filesystem.list"
    }

    fn description(&self) -> &'static str {
        "Melihat daftar berkas dan subfolder dalam direktori."
    }

    fn input_schema(&self) -> Value {
        json!({
            "type": "object",
            "properties": {
                "path": { "type": "string", "description": "Lokasi direktori (opsional, default: '.')" }
            }
        })
    }

    async fn execute(&self, args: Value) -> Result<Value, ToolError> {
        let path_str = args.get("path")
            .and_then(|v| v.as_str())
            .unwrap_or(".");

        let path = Path::new(path_str);
        if !path.exists() {
            return Err(ToolError::ExecutionFailed(format!("Direktori '{}' tidak ditemukan", path_str)));
        }

        let mut read_dir = tokio::fs::read_dir(path)
            .await
            .map_err(|e| ToolError::ExecutionFailed(e.to_string()))?;

        let mut entries = Vec::new();
        while let Ok(Some(entry)) = read_dir.next_entry().await {
            let file_name = entry.file_name().to_string_lossy().to_string();
            let is_dir = entry.file_type().await.map(|t| t.is_dir()).unwrap_or(false);
            let size = if is_dir { 0 } else { entry.metadata().await.map(|m| m.len()).unwrap_or(0) };
            entries.push(json!({
                "name": file_name,
                "is_directory": is_dir,
                "size_bytes": size
            }));
        }

        Ok(json!({
            "path": path_str,
            "total_items": entries.len(),
            "items": entries
        }))
    }
}

// 5. Shell Run Tool
pub struct ShellRunTool;

#[async_trait]
impl Tool for ShellRunTool {
    fn name(&self) -> &'static str {
        "shell.run"
    }

    fn description(&self) -> &'static str {
        "Menjalankan perintah command line di sistem lokal (PowerShell/CMD) dengan batas timeout."
    }

    fn input_schema(&self) -> Value {
        json!({
            "type": "object",
            "required": ["command"],
            "properties": {
                "command": { "type": "string", "description": "Perintah shell yang akan dijalankan" },
                "cwd": { "type": "string", "description": "Direktori kerja (opsional)" }
            }
        })
    }

    async fn execute(&self, args: Value) -> Result<Value, ToolError> {
        let cmd_str = args.get("command")
            .and_then(|v| v.as_str())
            .ok_or_else(|| ToolError::InvalidArguments("Parameter 'command' wajib diisi".to_string()))?;

        let cwd = args.get("cwd").and_then(|v| v.as_str()).unwrap_or(".");

        let output = tokio::process::Command::new("powershell")
            .args(["-NoProfile", "-Command", cmd_str])
            .current_dir(cwd)
            .output()
            .await
            .map_err(|e| ToolError::ExecutionFailed(e.to_string()))?;

        let stdout = String::from_utf8_lossy(&output.stdout).to_string();
        let stderr = String::from_utf8_lossy(&output.stderr).to_string();

        Ok(json!({
            "exit_code": output.status.code().unwrap_or(-1),
            "stdout": stdout,
            "stderr": stderr,
            "success": output.status.success()
        }))
    }
}
