pub mod builtin;
pub mod registry;

use agent_protocol::ToolDefinition;
use async_trait::async_trait;
use serde_json::Value;
use std::sync::Arc;
use thiserror::Error;

#[derive(Error, Debug)]
pub enum ToolError {
    #[error("Tool '{0}' not found")]
    NotFound(String),
    #[error("Invalid arguments: {0}")]
    InvalidArguments(String),
    #[error("Execution failed: {0}")]
    ExecutionFailed(String),
    #[error("Permission denied: {0}")]
    PermissionDenied(String),
}

#[async_trait]
pub trait Tool: Send + Sync {
    fn name(&self) -> &'static str;
    fn description(&self) -> &'static str;
    fn input_schema(&self) -> Value;
    async fn execute(&self, args: Value) -> Result<Value, ToolError>;

    fn definition(&self) -> ToolDefinition {
        ToolDefinition {
            name: self.name().to_string(),
            description: self.description().to_string(),
            input_schema: self.input_schema(),
        }
    }
}

pub type ArcTool = Arc<dyn Tool>;
