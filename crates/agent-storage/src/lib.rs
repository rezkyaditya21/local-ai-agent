use agent_core::Task;
use anyhow::Result;
use std::path::{Path, PathBuf};

pub struct TaskStorage {
    dir: PathBuf,
}

impl TaskStorage {
    pub fn new(dir: impl AsRef<Path>) -> Result<Self> {
        let dir = dir.as_ref().to_path_buf();
        std::fs::create_dir_all(&dir)?;
        Ok(Self { dir })
    }

    pub fn save_task(&self, task: &Task) -> Result<()> {
        let filename = format!("{}.json", task.id);
        let path = self.dir.join(filename);
        let json = serde_json::to_string_pretty(task)?;
        std::fs::write(path, json)?;
        Ok(())
    }

    pub fn load_task(&self, id: &str) -> Result<Task> {
        let path = self.dir.join(format!("{}.json", id));
        let data = std::fs::read_to_string(path)?;
        let task: Task = serde_json::from_str(&data)?;
        Ok(task)
    }

    pub fn list_tasks(&self) -> Result<Vec<Task>> {
        let mut tasks = Vec::new();
        if self.dir.exists() {
            for entry in std::fs::read_dir(&self.dir)? {
                let entry = entry?;
                let path = entry.path();
                if path.extension().map_or(false, |ext| ext == "json") {
                    if let Ok(content) = std::fs::read_to_string(&path) {
                        if let Ok(task) = serde_json::from_str::<Task>(&content) {
                            tasks.push(task);
                        }
                    }
                }
            }
        }
        Ok(tasks)
    }
}
