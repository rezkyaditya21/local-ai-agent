use crate::{ArcTool, Tool, ToolError};
use agent_protocol::ToolDefinition;
use std::collections::HashMap;
use std::sync::Arc;

#[derive(Default)]
pub struct ToolRegistry {
    tools: HashMap<String, ArcTool>,
}

impl ToolRegistry {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn register(&mut self, tool: impl Tool + 'static) {
        let name = tool.name().to_string();
        self.tools.insert(name, Arc::new(tool));
    }

    pub fn get(&self, name: &str) -> Result<ArcTool, ToolError> {
        self.tools
            .get(name)
            .cloned()
            .ok_or_else(|| ToolError::NotFound(name.to_string()))
    }

    pub fn list_definitions(&self) -> Vec<ToolDefinition> {
        self.tools.values().map(|t| t.definition()).collect()
    }
}
