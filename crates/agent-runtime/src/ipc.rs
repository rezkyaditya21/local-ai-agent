use agent_protocol::{IpcMessage, MessagePayload};
use anyhow::{anyhow, Result};
use std::process::Stdio;
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::process::{Child, ChildStdin, ChildStdout, Command};
use tracing::{error, info};
use uuid::Uuid;

pub struct PythonWorkerClient {
    _process: Child,
    stdin: ChildStdin,
    reader: tokio::io::Lines<BufReader<ChildStdout>>,
}

impl PythonWorkerClient {
    pub async fn spawn(python_bin: &str, script_path: &str) -> Result<Self> {
        info!("Spawning Python AI Worker: {} {}", python_bin, script_path);

        let mut child = Command::new(python_bin)
            .arg(script_path)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit())
            .spawn()?;

        let stdin = child.stdin.take().ok_or_else(|| anyhow!("Failed to open stdin"))?;
        let stdout = child.stdout.take().ok_or_else(|| anyhow!("Failed to open stdout"))?;
        let reader = BufReader::new(stdout).lines();

        Ok(Self {
            _process: child,
            stdin,
            reader,
        })
    }

    pub async fn send_request(&mut self, payload: MessagePayload) -> Result<MessagePayload> {
        let msg = IpcMessage {
            version: 1,
            id: Uuid::new_v4().to_string(),
            payload,
        };

        let mut line = serde_json::to_string(&msg)?;
        line.push('\n');
        self.stdin.write_all(line.as_bytes()).await?;
        self.stdin.flush().await?;

        if let Some(resp_line) = self.reader.next_line().await? {
            let resp: IpcMessage = serde_json::from_str(&resp_line)?;
            Ok(resp.payload)
        } else {
            Err(anyhow!("Python worker closed connection prematurely"))
        }
    }

    pub async fn ping(&mut self) -> Result<String> {
        let resp = self.send_request(MessagePayload::Ping).await?;
        match resp {
            MessagePayload::Pong { status, model } => {
                Ok(format!("{status} (Model: {})", model.unwrap_or_else(|| "none".into())))
            }
            MessagePayload::Error { message } => Err(anyhow!("Worker error: {}", message)),
            other => Err(anyhow!("Unexpected response: {:?}", other)),
        }
    }
}
