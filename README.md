# 🤖 Local AI Agent — Autonomous Engineering System

<p align="center">
  <a href="https://github.com/rezkyaditya21/local-ai-agent"><img src="https://img.shields.io/badge/Python-3.11%2B-blue?style=for-the-badge&logo=python" alt="Python 3.11+"></a>
  <a href="https://github.com/rezkyaditya21/local-ai-agent"><img src="https://img.shields.io/badge/Tests-100%25%20Passed-brightgreen?style=for-the-badge&logo=pytest" alt="Pytest Passed"></a>
  <a href="https://github.com/rezkyaditya21/local-ai-agent"><img src="https://img.shields.io/badge/Architecture-Autonomous%20Loop-orange?style=for-the-badge" alt="Autonomous AI Agent"></a>
  <a href="https://github.com/rezkyaditya21/local-ai-agent"><img src="https://img.shields.io/badge/Backend-GGUF%20(llama--cpp--python)-purple?style=for-the-badge" alt="GGUF Backend"></a>
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
- **⚡ GGUF Local Model Support**: Menjalankan model kuantisasi GGUF secara langsung dan efisien menggunakan `llama-cpp-python` tanpa ketergantungan server eksternal.

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
- Model berformat `.gguf` (misalnya Qwen 2.5 Coder 7B GGUF)

### 2. Instalasi
```powershell
# Clone repository
git clone https://github.com/rezkyaditya21/local-ai-agent.git
cd local-ai-agent

# Install dependensi
pip install -e .
pip install -e .[test]
```

### 3. Konfigurasi Model GGUF (`config.toml`)
Tentukan path file model `.gguf` Anda pada file `config.toml`:

```toml
default_model = "qwen7b"

[[models]]
name = "qwen7b"
model_type = "gguf"
path_or_url = "C:/path/ke/model_anda.gguf"
```

### 4. Menjalankan Agent

**Mode Desktop GUI (Native Window / Webview):**
```powershell
python run_desktop.py
# atau
agent-desktop
```

**Mode Terminal CLI:**
```powershell
python -m agent
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
│   ├── desktop/           # Desktop GUI (PyWebView, Bridge & Modern Web UI)
│   ├── memory/            # Multi-Tiered Memory System (Working & Long-Term)
│   ├── models/            # Model Manager (GGUF loader via llama-cpp-python)
│   ├── self_improvement/  # Checkpoint Manager & Controlled Experiment Engine
│   └── tools/             # 13 Built-in Engineering & System Tools
├── tests/
│   └── unit/              # Unit test suites (224 tests)
├── run_desktop.py         # Shortcut launcher for Desktop GUI
├── config.toml            # Application & GGUF Model configuration
└── pyproject.toml         # Package definition & dependencies
```

---

## 📜 License

Project dipublikasikan di bawah lisensi [MIT License](LICENSE).
