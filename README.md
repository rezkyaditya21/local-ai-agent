# Local AI Agent — High-Performance Autonomous Engineering Platform

<p align="center">
  <img src="https://img.shields.io/badge/Rust-2021%20Edition-orange?style=for-the-badge&logo=rust" alt="Rust 2021">
  <img src="https://img.shields.io/badge/Python-3.11%2B-blue?style=for-the-badge&logo=python" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/Architecture-Rust%20Runtime%20%2B%20Python%20AI-red?style=for-the-badge" alt="Hybrid Architecture">
  <img src="https://img.shields.io/badge/LLM-Local%20GGUF%20(Qwen%202.5%20Coder)-purple?style=for-the-badge" alt="Local GGUF">
  <img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License MIT">
</p>

---

## Overview

**Local AI Agent** adalah platform agen AI otonom (*Autonomous AI Agent Platform*) berkinerja tinggi yang menggabungkan keandalan sistem **Rust** sebagai otoritas eksekusi (*Runtime Authority*) dan fleksibilitas **Python** sebagai mesin penalaran kecerdasan buatan (*AI Worker*).

Platform ini berjalan **100% lokal dan offline** di komputer Anda tanpa memerlukan API cloud berbayar atau koneksi internet eksternal. Ditenagai oleh model lokal berformat GGUF (seperti **Qwen 2.5 Coder 7B** via `llama-cpp-python`), platform ini mampu merencanakan (*plan*), mengeksekusi (*act*), mengobservasi (*observe*), dan memverifikasi (*verify*) tugas-tugas rekayasa secara otonom.

---

## Core Architecture

Sistem ini menganut filosofi:
> **Rust = Brain Infrastructure, Policy, Safety, and Native Tool Execution**  
> **Python = LLM Inference, Context Engineering, and High-Level Reasoning**  
> **Standard IPC = Structured JSON Lines over Stdio Streams**

```text
+-----------------------------------------------------------------------+
|                            USER INTERFACE                             |
|        Native CLI (agent.exe)         |    Web Desktop Dashboard      |
+---------------------------------------+-------------------------------+
                                    |
                                    v
+-----------------------------------------------------------------------+
|                    RUST RUNTIME (AUTHORITY LAYER)                     |
|                                                                       |
|  [ agent-core ]       [ agent-state ]        [ agent-execution ]      |
|  Entity Models        State Machine          Sandboxing & Timeout     |
|                                                                       |
|  [ agent-tools ]      [ agent-storage ]      [ agent-observability ]  |
|  Native Tool Runner   Atomic JSON Persistence Structured Tracing       |
+-----------------------------------------------------------------------+
                                    |
                    IPC Protocol: JSON Lines (Stdio)
                                    |
                                    v
+-----------------------------------------------------------------------+
|                     PYTHON AI ENGINE (WORKER LAYER)                   |
|                                                                       |
|  [ LocalModelBackend ]            [ Heuristic & LLM Planner ]         |
|  llama-cpp-python GGUF Driver     Decision & Task Decomposition Engine|
|  (Qwen 2.5 Coder 7B Instruct)                                         |
+-----------------------------------------------------------------------+
```

---

## Workspace Crates Structure

Repositori ini disusun dalam monorepo modular 9 Crate Rust:

| Crate | Direktori | Tanggung Jawab |
|---|---|---|
| **agent-protocol** | `crates/agent-protocol` | Kontrak tipe data IPC (JSON Lines v1), skema pesan `decision_request`, `decision_response`, tool definitions. |
| **agent-core** | `crates/agent-core` | Model entitas inti: `Task`, `StepRecord`, `ToolObservation`, `TaskStatus`, `Session`. |
| **agent-state** | `crates/agent-state` | Mesin state siklus hidup agen (`Pending` -> `Planning` -> `Executing` -> `Verifying` -> `Completed`). |
| **agent-tools** | `crates/agent-tools` | Registri & eksekutor tool native (`system.info`, `filesystem.read`, `filesystem.write`, `shell.run`). |
| **agent-execution** | `crates/agent-execution` | Kebijakan eksekusi aman, timeout, sandbox boundary, anti-loop safeguards. |
| **agent-storage** | `crates/agent-storage` | Penyimpanan persisten atomik task & session berbasis JSON di `storage/tasks/`. |
| **agent-observability** | `crates/agent-observability` | Tracing terstruktur, log terpadu, jejak audit transparan. |
| **agent-runtime** | `crates/agent-runtime` | Otak loop kontrol otonom & jembatan IPC Stdio ke worker Python. |
| **agent-cli** | `crates/agent-cli` | Antarmuka CLI native (`doctor`, `tools`, `task`, `history`). |

---

## Key Features

- **100% Offline & Private**: Seluruh data tersimpan lokal di mesin Anda. Tidak ada telemetri eksternal atau dependensi cloud.
- **Dual Interface**:
  - **Native CLI**: Eksekusi instan dan hemat sumber daya via binary Rust `agent.exe` atau `agent.bat`.
  - **Web Desktop UI**: Dashboard interaktif berbasis browser lokal (`python run_desktop.py`).
- **Autonomous Execution Loop**: Mampu memecah tujuan menjadi langkah-langkah terstruktur (`Observe` -> `Analyze` -> `Plan` -> `Act` -> `Verify`).
- **Safety Guardrails**: Pembatasan iterasi maksimum, timeout perintah terminal, dan validasi izin tool.
- **Audit Trail & Persistence**: Setiap pemikiran (*thought*), tindakan (*action*), dan observasi (*observation*) disimpan dalam format JSON terstruktur.

---

## Quick Start Guide

### Prasyarat
- **Rust Toolchain** (1.75+ atau 1.98+ dengan target `x86_64-pc-windows-gnu` atau MSVC).
- **Python 3.11+** dengan `llama-cpp-python` terpasang.
- File model GGUF (default: `qwen2.5-coder-7b-instruct-q4_k_m.gguf`).

### 1. Kompilasi Binary Rust
```bash
# Periksa integritas workspace
cargo check --workspace

# Bangun binary release teroptimasi
cargo build --release -p agent-cli
```

### 2. Jalankan Diagnostik Sistem
```cmd
agent.bat doctor
```
Output:
```text
========================================
   AUTONOMOUS AGENT SYSTEM DOCTOR
========================================
RUST CORE           : [OK] v0.1.0
PYTHON RUNTIME      : [OK] Python 3.11.9
IPC PROTOCOL        : [OK] JSON Lines v1
PYTHON WORKER IPC   : [OK] ready (Model: qwen2.5-coder-7b)
PLATFORM LOCATION   : E:gent_system (atau direktori repositori)
========================================
```

### 3. Eksekusi Tugas Otonom
```cmd
# Pertanyaan langsung / penalaran AI
agent.bat task "kamu ai apa"

# Tugas inspeksi dan telemetri sistem
agent.bat task "Inspeksi telemetri sistem dan laporkan spesifikasi"

# Menjalankan perintah terminal lokal
agent.bat task "Jalankan perintah shell untuk melihat daftar file"
```

### 4. Periksa Riwayat Tugas
```cmd
agent.bat history
```

---

## Konfigurasi (`config.toml`)

Konfigurasi sistem dapat disesuaikan pada file `config.toml`:

```toml
[platform]
name = "Autonomous Agent Platform"
version = "0.1.0"

[runtime]
max_iterations = 15
execution_timeout_seconds = 300

[python]
executable = "python"
worker_script = "./python/ai_engine/worker.py"

[model]
model_path = "C:/Users/rezky/Documents/models/qwen2.5-coder-7b-instruct-q4_k_m.gguf"
context_length = 2048
temperature = 0.2
```

---

## Lisensi

Proyek ini dirilis di bawah lisensi [MIT](LICENSE).\n