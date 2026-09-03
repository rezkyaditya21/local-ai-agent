pub mod ipc;

use agent_core::{StepRecord, Task, TaskStatus};
use agent_execution::ExecutionPolicy;
use agent_protocol::{AgentAction, MessagePayload, ToolObservation};
use agent_state::{State, StateMachine};
use agent_tools::builtin::{FileListTool, FileReadTool, FileWriteTool, ShellRunTool, SystemInfoTool};
use agent_tools::registry::ToolRegistry;
use anyhow::{anyhow, Result};
use chrono::Utc;
use ipc::PythonWorkerClient;
use tracing::{info, warn};

pub struct AgentRuntime {
    registry: ToolRegistry,
    policy: ExecutionPolicy,
    max_iterations: u32,
}

impl AgentRuntime {
    pub fn new(max_iterations: u32) -> Self {
        let mut registry = ToolRegistry::new();
        registry.register(SystemInfoTool);
        registry.register(FileReadTool);
        registry.register(FileWriteTool);
        registry.register(FileListTool);
        registry.register(ShellRunTool);

        Self {
            registry,
            policy: ExecutionPolicy::default(),
            max_iterations,
        }
    }

    pub fn tool_registry(&self) -> &ToolRegistry {
        &self.registry
    }

    pub async fn execute_goal(
        &self,
        goal: &str,
        worker: &mut PythonWorkerClient,
    ) -> Result<Task> {
        self.execute_goal_streaming(goal, worker, |_| {}).await
    }

    pub async fn execute_goal_streaming<F>(
        &self,
        goal: &str,
        worker: &mut PythonWorkerClient,
        mut on_token: F,
    ) -> Result<Task>
    where
        F: FnMut(&str),
    {
        info!("Memulai tugas otonom: '{}'", goal);
        let mut task = Task::new(goal);
        task.status = TaskStatus::Running;

        let mut sm = StateMachine::new(self.max_iterations);
        sm.transition(State::Analyzing);

        let tools = self.registry.list_definitions();
        let mut context = String::from("Sistem baru dimulai.");

        while !sm.is_exhausted() {
            sm.transition(State::Planning);

            let req = MessagePayload::DecisionRequest {
                goal: task.goal.clone(),
                iteration: sm.iteration() + 1,
                context: context.clone(),
                available_tools: tools.clone(),
            };

            let resp = worker.send_request_streaming(req, &mut on_token).await?;
            let (thought, action) = match resp {
                MessagePayload::DecisionResponse { thought, action } => (thought, action),
                MessagePayload::Error { message } => return Err(anyhow!("Python error: {message}")),
                other => return Err(anyhow!("Unexpected response from Python: {:?}", other)),
            };

            info!("[Iterasi {}] Thought: {}", sm.iteration() + 1, thought);

            match action {
                AgentAction::Finish { summary } => {
                    info!("Agent menyatakan tugas selesai: {}", summary);
                    task.status = TaskStatus::Completed;
                    task.history.push(StepRecord {
                        iteration: sm.iteration() + 1,
                        thought,
                        action: AgentAction::Finish { summary },
                        observation: None,
                        timestamp: Utc::now(),
                    });
                    sm.transition(State::Completed);
                    return Ok(task);
                }
                AgentAction::ToolCall { tool, arguments } => {
                    sm.transition(State::Executing);
                    info!("Memanggil tool: '{}' dengan args: {}", tool, arguments);

                    let obs = match self.registry.get(&tool) {
                        Ok(t) => match t.execute(arguments.clone()).await {
                            Ok(data) => {
                                info!("Tool '{}' berhasil dieksekusi", tool);
                                ToolObservation {
                                    tool: tool.clone(),
                                    success: true,
                                    data,
                                    error: None,
                                }
                            }
                            Err(e) => {
                                warn!("Tool '{}' gagal: {}", tool, e);
                                ToolObservation {
                                    tool: tool.clone(),
                                    success: false,
                                    data: serde_json::Value::Null,
                                    error: Some(e.to_string()),
                                }
                            }
                        },
                        Err(e) => ToolObservation {
                            tool: tool.clone(),
                            success: false,
                            data: serde_json::Value::Null,
                            error: Some(e.to_string()),
                        },
                    };

                    context = format!("Hasil tool terakhir: {}", serde_json::to_string(&obs)?);

                    task.history.push(StepRecord {
                        iteration: sm.iteration(),
                        thought,
                        action: AgentAction::ToolCall { tool, arguments },
                        observation: Some(obs),
                        timestamp: Utc::now(),
                    });

                    sm.transition(State::Observing);
                }
            }
        }

        task.status = TaskStatus::Failed;
        sm.transition(State::Failed);
        Ok(task)
    }
}
