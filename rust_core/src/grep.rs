use regex::Regex;
use serde::{Deserialize, Serialize};
use std::fs::File;
use std::io::{BufRead, BufReader};
use std::path::Path;
use walkdir::WalkDir;

#[derive(Serialize, Deserialize, Debug)]
pub struct GrepMatch {
    pub file: String,
    pub line_number: usize,
    pub content: String,
}

#[derive(Serialize, Deserialize, Debug)]
pub struct GrepResult {
    pub query: String,
    pub total_matches: usize,
    pub matches: Vec<GrepMatch>,
}

pub fn grep_code(root_path: &str, query: &str, is_regex: bool, max_matches: usize) -> GrepResult {
    let re = if is_regex {
        Regex::new(query).ok()
    } else {
        Regex::new(&regex::escape(query)).ok()
    };

    let mut matches = Vec::new();

    if let Some(pattern) = re {
        let code_extensions = ["rs", "py", "js", "ts", "php", "html", "css", "json", "toml", "md", "sql"];

        for entry in WalkDir::new(root_path)
            .into_iter()
            .filter_map(|e| e.ok())
            .filter(|e| e.file_type().is_file())
        {
            let path = entry.path();
            let ext = path.extension().and_then(|s| s.to_str()).unwrap_or("");
            if !code_extensions.contains(&ext) {
                continue;
            }

            // Skip heavy build directories
            let path_str = path.to_string_lossy();
            if path_str.contains("node_modules")
                || path_str.contains("target")
                || path_str.contains(".git")
                || path_str.contains("__pycache__")
                || path_str.contains(".venv")
            {
                continue;
            }

            if let Ok(file) = File::open(path) {
                let reader = BufReader::new(file);
                for (line_idx, line_res) in reader.lines().enumerate() {
                    if let Ok(line) = line_res {
                        if pattern.is_match(&line) {
                            matches.push(GrepMatch {
                                file: path_str.to_string(),
                                line_number: line_idx + 1,
                                content: line.trim().to_string(),
                            });
                            if matches.len() >= max_matches {
                                return GrepResult {
                                    query: query.to_string(),
                                    total_matches: matches.len(),
                                    matches,
                                };
                            }
                        }
                    }
                }
            }
        }
    }

    GrepResult {
        query: query.to_string(),
        total_matches: matches.len(),
        matches,
    }
}
