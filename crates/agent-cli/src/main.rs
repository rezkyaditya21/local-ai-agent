use agent_observability::init_observability;
use agent_runtime::ipc::PythonWorkerClient;
use agent_runtime::AgentRuntime;
use agent_storage::TaskStorage;
use clap::{Parser, Subcommand};
use std::path::Path;

#[derive(Parser)]
#[command(name = "agent")]
#[command(about = "High-Performance Rust + Python Hybrid Autonomous AI Agent Platform", long_about = None)]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Periksa status kesehatan seluruh sistem agent (Doctor)
    Doctor,
    /// Tampilkan daftar tool yang terdaftar
    Tools,
    /// Jalankan tugas otonom secara mandiri
    Task {
        /// Tujuan atau instruksi tugas
        goal: String,
        /// Batas maksimum iterasi tindakan
        #[arg(short, long, default_value_t = 10)]
        max_iterations: u32,
    },
    /// Tampilkan riwayat tugas yang pernah dieksekusi
    History,
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    init_observability();
    let cli = Cli::parse();

    let python_bin = "python";
    let worker_script = "E:\\agent_system\\python\\ai_engine\\worker.py";
    let storage_dir = "E:\\agent_system\\storage\\tasks";

    match cli.command {
        Commands::Doctor => {
            println!("========================================");
            println!("   AUTONOMOUS AGENT SYSTEM DOCTOR");
            println!("========================================");
            println!("RUST CORE           : [OK] v0.1.0");

            let py_status = tokio::process::Command::new(python_bin)
                .arg("--version")
                .output()
                .await;

            match py_status {
                Ok(out) => println!("PYTHON RUNTIME      : [OK] {}", String::from_utf8_lossy(&out.stdout).trim()),
                Err(e) => println!("PYTHON RUNTIME      : [FAILED] {}", e),
            }

            println!("IPC PROTOCOL        : [OK] JSON Lines v1");

            if Path::new(worker_script).exists() {
                match PythonWorkerClient::spawn(python_bin, worker_script).await {
                    Ok(mut client) => match client.ping().await {
                        Ok(pong) => println!("PYTHON WORKER IPC   : [OK] {}", pong),
                        Err(e) => println!("PYTHON WORKER IPC   : [FAILED] {}", e),
                    },
                    Err(e) => println!("PYTHON WORKER SPAWN : [FAILED] {}", e),
                }
            } else {
                println!("PYTHON WORKER FILE  : [NOT FOUND] {}", worker_script);
            }

            println!("PLATFORM LOCATION   : E:\\agent_system");
            println!("========================================");
        }
        Commands::Tools => {
            let runtime = AgentRuntime::new(10);
            let tools = runtime.tool_registry().list_definitions();
            println!("Daftar Tool Tersedia ({} Tools):", tools.len());
            for t in tools {
                println!("  - {:<20} : {}", t.name, t.description);
            }
        }
        Commands::Task { goal, max_iterations } => {
            println!("Menjalankan Tugas Otonom: '{}'", goal);
            let runtime = AgentRuntime::new(max_iterations);
            let mut worker = PythonWorkerClient::spawn(python_bin, worker_script).await?;
            let task = runtime.execute_goal(&goal, &mut worker).await?;

            println!("========================================");
            println!("Status Akhir: {:?}", task.status);
            println!("Langkah Selesai: {} iterasi", task.history.len());

            if let Some(last_step) = task.history.last() {
                if let agent_protocol::AgentAction::Finish { ref summary } = last_step.action {
                    println!("\n[Jawaban / Hasil AI]:\n{}", summary);
                }
            }
            
            let storage = TaskStorage::new(storage_dir)?;
            storage.save_task(&task)?;
            println!("Data tersimpan: {}\\{}.json", storage_dir, task.id);
            println!("========================================");
        }
        Commands::History => {
            let storage = TaskStorage::new(storage_dir)?;
            let tasks = storage.list_tasks()?;
            println!("Riwayat Eksekusi Tugas (Total: {}):", tasks.len());
            if tasks.is_empty() {
                println!("  (Belum ada riwayat tugas)");
            } else {
                for (idx, t) in tasks.iter().enumerate() {
                    let id_str = t.id.to_string(); let id_prefix = &id_str[..8];
                    println!("  [{}] ID: {} | Goal: '{}' | Status: {:?}", idx + 1, id_prefix, t.goal, t.status);
                }
            }
        }
    }

    Ok(())
}
