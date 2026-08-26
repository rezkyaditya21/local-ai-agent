# 🤖 Local AI Agent — Autonomous Engineering System

<p align="center">
  <a href="https://github.com/rezkyaditya21/local-ai-agent"><img src="https://img.shields.io/badge/Python-3.11%2B-blue?style=for-the-badge&logo=python" alt="Python 3.11+"></a>
  <a href="https://github.com/rezkyaditya21/local-ai-agent"><img src="https://img.shields.io/badge/Tests-100%25%20Passed-brightgreen?style=for-the-badge&logo=pytest" alt="Pytest Passed"></a>
  <a href="https://github.com/rezkyaditya21/local-ai-agent"><img src="https://img.shields.io/badge/Architecture-Autonomous%20Loop-orange?style=for-the-badge" alt="Autonomous AI Agent"></a>
  <a href="https://github.com/rezkyaditya21/local-ai-agent"><img src="https://img.shields.io/badge/Backend-Ollama%20%7C%20GGUF-purple?style=for-the-badge" alt="Ollama & GGUF"></a>
  <a href="https://github.com/rezkyaditya21/local-ai-agent/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License MIT"></a>
</p>

---

## 🌟 Overview

**Local AI Agent** adalah sistem AI otonom (*Autonomous Local AI Agent System*) berbasis terminal yang berjalan 100% di komputer lokal Anda. Berbeda dari chatbot konvensional, agent ini mampu mengeksekusi tugas rekayasa perangkat lunak secara mandiri menggunakan 13 *engineering tools*, sistem memori berlapis, perencanaan multi-langkah (*planner*), serta mesin eksperimen perbaikan mandiri (*self-improvement engine*) dengan pemulihan otomatis (*checkpoint/rollback*).

---

## ✨ Key Features

- **🔄 Autonomous Execution Loop**: Siklus otonom mandiri (`OBSERVE -> ANALYZE -> PLAN -> ACT -> TEST -> EVALUATE -> IMPROVE -> REPEAT`) untuk menyelesaikan tugas kompleks secara terus-menerus.
- **🧰 13 Engineering Tools Built-in**:
  - `code_search`: Pencarian simbol, kelas, fungsi, dan regex di seluruh berkas proyek.
  - `git`: Status, diff, commit, log, checkpoint, dan rollback Git.
  - `test_runner`: Eksekusi pengujian otomatis `pytest` & parsing error stack traces.
  - `python_exec`: Eksekusi aman cuplikan kode Python di runtime terisolasi.
  - `system_inspect`: Inspeksi lingkungan OS, versi Python, dan paket terinstal.
  - `project_inspect`: Analisis struktur repositori & dependensi (`pyproject.toml`).
  - `benchmark`: Pengukuran durasi eksekusi dan perbandingan performa kode.
  - `web_search`: Pencarian internet *real-time* via Bing/DuckDuckGo parser.
  - `filesystem`, `shell`, `browser`, `database`, `http_api`.
- **🧠 Multi-Tiered Memory System**: Memisahkan *Working Memory* (tugas aktif), *Long-Term Memory* (penyimpanan permanen aturan & fakta), dan *Project Knowledge*.
- **📊 Multi-Step Goal Planner**: Memecah instruksi kompleks menjadi `Goal -> Subtasks -> Actions -> Verification -> Result`.
- **🛡️ Checkpoint & Rollback Recovery Engine**: Membuat snapshot repositori otomatis sebelum modifikasi kode dan memulihkan (*rollback*) jika pengujian gagal.
- **⚡ Dual Backend Support (Ollama & GGUF)**: Dukungan *hot-swap* model API Ollama atau file `.gguf` lokal langsung tanpa restart.

---

## 🏗️ Architecture

```
                                 ┌─────────────────────────────────┐
                                 │       Terminal CLI REPL         │
                                 └────────────────┬────────────────┘
                                                  │
                                 ┌────────────────▼────────────────┐
                                 │   Agent Orchestrator & Loop     │
                                 └───────┬────────┬────────┬───────┘
                                         │        │        │
               ┌─────────────────────────┘        │        └─────────────────────────┐
               ▼                                  ▼                                  ▼
 ┌───────────────────────────┐      ┌───────────────────────────┐      ┌───────────────────────────┐
 │   Multi-Step Planner      │      │    Multi-Tier Memory     │      │   System Self-Inspector   │
 └───────────────────────────┘      └───────────────────────────┘      └───────────────────────────┘
               │                                  │                                  │
               └─────────────────────────┐        │        ┌─────────────────────────┘
                                         ▼        ▼        ▼
                                 ┌─────────────────────────────────┐
                                 │     Executor & Safety Gate      │
                                 └────────────────┬────────────────┘
                                                  │
                                 ┌────────────────▼────────────────┐
                                 │ 13 Engineering & System Tools   │
                                 └─────────────────────────────────┘
```

---

## 🚀 Quick Start

### 1. Prasyarat System
- Python 3.11 atau lebih baru
- [Ollama](https://ollama.com) (Opsional, jika memilih backend API Ollama)

### 2. Instalasi
```powershell
# Clone repository
git clone https://github.com/rezkyaditya21/local-ai-agent.git
cd local-ai-agent

# Install dependensi
pip install -e .
pip install -e .[test]
```

### 3. Mengunduh Model (Ollama)
```powershell
ollama pull llama3.2:3b
```

### 4. Menjalankan Agent
```powershell
python -m agent
```

---

## ⚙️ Multi-Model Configuration (`config.toml`)

Anda dapat mendaftarkan beberapa model sekaligus di berkas `config.toml`:

```toml
default_model = "llama3.2:3b"

# Opsi 1: Model via Ollama API
[[models]]
name = "llama3.2:3b"
model_type = "api"
path_or_url = "http://localhost:11434"

# Opsi 2: Model GGUF Lokal Langsung
[[models]]
name = "model_gguf_lokal"
model_type = "gguf"
path_or_url = "C:/path/ke/model_anda.gguf"
```

Beralih model saat aplikasi berjalan:
```text
> /model switch model_gguf_lokal
```

---

## 🧪 Running Automated Tests

Seluruh modul dan alat dilengkapi dengan unit tes komprehensif (100% Passed):

```powershell
python -m pytest
```

---

## 📂 Project Structure

```text
local-ai-agent/
├── agent/
│   ├── cli/               # CLI REPL interface & Rich formatting
│   ├── core/              # Orchestrator, Planner, System Inspector, Executor
│   ├── memory/            # Multi-Tiered Memory System (Working & Long-Term)
│   ├── models/            # Model Manager (Ollama API & GGUF loader)
│   ├── self_improvement/  # Checkpoint Manager & Controlled Experiment Engine
│   └── tools/             # 13 Built-in Engineering & System Tools
├── tests/
│   └── unit/              # 142 Unit test suites
├── config.toml            # Application & Multi-model configuration
└── pyproject.toml         # Package definition & dependencies
```

---

## 📜 License

Project dipublikasikan di bawah lisensi [MIT License](LICENSE).
