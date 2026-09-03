use agent_observability::init_observability;
use agent_runtime::ipc::PythonWorkerClient;
use agent_runtime::AgentRuntime;
use agent_storage::TaskStorage;
use clap::{Parser, Subcommand};
use std::io::{self, Write};
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
    /// Jalankan tugas otonom secara mandiri (sekali jalan)
    Task {
        /// Tujuan atau instruksi tugas
        goal: String,
        /// Batas maksimum iterasi tindakan
        #[arg(short, long, default_value_t = 10)]
        max_iterations: u32,
    },
    /// Tampilkan riwayat tugas yang pernah dieksekusi
    History,
    /// Masuk ke Mode Percakapan Interaktif (Chat REPL dengan Live Streaming)
    Chat,
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let cli = Cli::parse();
    // In chat mode, quiet telemetry so conversation UI is 100% clean like ChatGPT!
    let quiet = matches!(cli.command, Commands::Chat);
    init_observability(quiet);

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
            println!("\nData tersimpan: {}\\{}.json", storage_dir, task.id);
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
                    let id_str = t.id.to_string();
                    let id_prefix = if id_str.len() >= 8 { &id_str[..8] } else { &id_str };
                    println!("  [{}] ID: {} | Goal: '{}' | Status: {:?}", idx + 1, id_prefix, t.goal, t.status);
                }
            }
        }
        Commands::Chat => {
            println!("==========================================================");
            println!("       AUTONOMOUS AGENT INTERACTIVE CHAT (REPL)           ");
            println!("  Ketik pertanyaan/perintah Anda. Ketik 'exit' untuk selesai. ");
            println!("==========================================================");

            print!("[1/2] Menghubungkan ke AI Engine & Memuat Model ke RAM... ");
            io::stdout().flush()?;
            let mut worker = PythonWorkerClient::spawn(python_bin, worker_script).await?;
            let pong = worker.ping().await?;
            println!("[OK]");
            println!("[2/2] Model Aktif: {}\n", pong);
            println!("--- Sesi Obrolan Aktif (Model Siap Standby di RAM) ---");

            let runtime = AgentRuntime::new(10);
            let storage = TaskStorage::new(storage_dir)?;

            loop {
                print!("\nAnda: ");
                io::stdout().flush()?;

                let mut input = String::new();
                if io::stdin().read_line(&mut input).is_err() {
                    break;
                }

                let trimmed = input.trim();
                if trimmed.is_empty() {
                    continue;
                }

                if trimmed.eq_ignore_ascii_case("exit")
                    || trimmed.eq_ignore_ascii_case("keluar")
                    || trimmed.eq_ignore_ascii_case("quit")
                    || trimmed.eq_ignore_ascii_case("q")
                {
                    println!("\nSampai jumpa! Sesi obrolan ditutup.");
                    break;
                }

                print!("AI: ");
                io::stdout().flush()?;
                let mut streamed_any = false;

                match runtime.execute_goal_streaming(trimmed, &mut worker, |token| {
                    print!("{}", token);
                    let _ = io::stdout().flush();
                    streamed_any = true;
                }).await {
                    Ok(task) => {
                        if !streamed_any {
                            if let Some(last_step) = task.history.last() {
                                if let agent_protocol::AgentAction::Finish { ref summary } = last_step.action {
                                    println!("{}", summary);
                                }
                            }
                        } else {
                            println!();
                        }
                        let _ = storage.save_task(&task);
                    }
                    Err(e) => {
                        println!("\n[Error]: Gagal memproses instruksi: {}", e);
                    }
                }
            }
        }
    }

    Ok(())
}
