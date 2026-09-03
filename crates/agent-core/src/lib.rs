use agent_protocol::{AgentAction, ToolObservation};
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Task {
    pub id: Uuid,
    pub goal: String,
    pub status: TaskStatus,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
    pub history: Vec<StepRecord>,
}

impl Task {
    pub fn new(goal: impl Into<String>) -> Self {
        let now = Utc::now();
        Self {
            id: Uuid::new_v4(),
            goal: goal.into(),
            status: TaskStatus::Pending,
            created_at: now,
            updated_at: now,
            history: Vec::new(),
        }
    }
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
pub enum TaskStatus {
    Pending,
    Running,
    Completed,
    Failed,
    Cancelled,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StepRecord {
    pub iteration: u32,
    pub thought: String,
    pub action: AgentAction,
    pub observation: Option<ToolObservation>,
    pub timestamp: DateTime<Utc>,
}
