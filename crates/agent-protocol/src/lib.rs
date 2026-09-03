use serde::{Deserialize, Serialize};
use serde_json::Value;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct IpcMessage {
    pub version: u32,
    pub id: String,
    #[serde(flatten)]
    pub payload: MessagePayload,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(tag = "type", content = "data")]
pub enum MessagePayload {
    #[serde(rename = "ping")]
    Ping,
    #[serde(rename = "pong")]
    Pong { status: String, model: Option<String> },

    #[serde(rename = "generate_request")]
    GenerateRequest {
        prompt: String,
        max_tokens: Option<u32>,
        temperature: Option<f32>,
        stop: Option<Vec<String>>,
    },
    #[serde(rename = "generate_response")]
    GenerateResponse {
        text: String,
        tokens_used: u32,
    },

    #[serde(rename = "decision_request")]
    DecisionRequest {
        goal: String,
        iteration: u32,
        context: String,
        available_tools: Vec<ToolDefinition>,
    },
    #[serde(rename = "decision_response")]
    DecisionResponse {
        thought: String,
        action: AgentAction,
    },

    #[serde(rename = "error")]
    Error { message: String },
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ToolDefinition {
    pub name: String,
    pub description: String,
    pub input_schema: Value,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(tag = "type", content = "details")]
pub enum AgentAction {
    #[serde(rename = "tool_call")]
    ToolCall {
        tool: String,
        arguments: Value,
    },
    #[serde(rename = "finish")]
    Finish {
        summary: String,
    },
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ToolObservation {
    pub tool: String,
    pub success: bool,
    pub data: Value,
    pub error: Option<String>,
}
