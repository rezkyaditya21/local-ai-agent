use serde::{Deserialize, Serialize};
use std::path::Path;
use walkdir::WalkDir;

#[derive(Serialize, Deserialize, Debug)]
pub struct FileEntry {
    pub path: String,
    pub name: String,
    pub is_dir: bool,
    pub size_bytes: u64,
}

#[derive(Serialize, Deserialize, Debug)]
pub struct ScanResult {
    pub root: String,
    pub total_files: usize,
    pub total_dirs: usize,
    pub total_size_mb: f64,
    pub entries: Vec<FileEntry>,
}

pub fn scan_directory(root_path: &str, max_depth: usize, max_results: usize) -> ScanResult {
    let mut entries = Vec::new();
    let mut total_files = 0;
    let mut total_dirs = 0;
    let mut total_bytes = 0u64;

    for entry in WalkDir::new(root_path)
        .max_depth(max_depth)
        .into_iter()
        .filter_map(|e| e.ok())
    {
        let is_dir = entry.file_type().is_dir();
        let size = if is_dir { 0 } else { entry.metadata().map(|m| m.len()).unwrap_or(0) };

        if is_dir {
            total_dirs += 1;
        } else {
            total_files += 1;
            total_bytes += size;
        }

        if entries.len() < max_results {
            entries.push(FileEntry {
                path: entry.path().to_string_lossy().to_string(),
                name: entry.file_name().to_string_lossy().to_string(),
                is_dir,
                size_bytes: size,
            });
        }
    }

    ScanResult {
        root: root_path.to_string(),
        total_files,
        total_dirs,
        total_size_mb: ((total_bytes as f64 / 1_048_576.0) * 100.0).round() / 100.0,
        entries,
    }
}
