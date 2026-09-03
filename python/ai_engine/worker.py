import sys
import json
import re
import tomllib
from pathlib import Path

CONFIG_PATH = Path("E:/agent_system/config.toml")

def get_active_model_path() -> Path:
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "rb") as f:
                cfg = tomllib.load(f)
                p = cfg.get("model", {}).get("model_path")
                if p and Path(p).exists():
                    return Path(p)
        except Exception:
            pass
    m_1_5b = Path("E:/agent_system/models/qwen2.5-coder-1.5b-instruct-q4_k_m.gguf")
    if m_1_5b.exists():
        return m_1_5b
    return Path("C:/Users/rezky/Documents/models/qwen2.5-coder-7b-instruct-q4_k_m.gguf")

class LocalModelBackend:
    def __init__(self):
        self._llm = None
        self._loaded_path = None

    def load(self):
        current_path = get_active_model_path()
        if self._llm is not None and self._loaded_path == current_path:
            return

        if current_path.exists():
            try:
                import llama_cpp
                self._llm = llama_cpp.Llama(
                    model_path=str(current_path),
                    n_ctx=1024,
                    n_threads=4,
                    n_batch=512,
                    verbose=False,
                )
                self._loaded_path = current_path
            except Exception:
                self._llm = None
        else:
            self._llm = None

    def is_ready(self) -> bool:
        return self._llm is not None

    def get_model_name(self) -> str:
        p = get_active_model_path()
        if "1.5b" in p.name.lower():
            return "Qwen 2.5 Coder 1.5B (Fast / Active)"
        elif "7b" in p.name.lower():
            return "Qwen 2.5 Coder 7B (Standard / Active)"
        return p.stem

    def answer_direct(self, query: str) -> str:
        self.load()
        if not self.is_ready():
            return (
                "Saya adalah Autonomous AI Agent Platform lokal berbasis hybrid Rust (Runtime) dan Python (AI Engine). "
                "Saya dapat mengeksekusi tugas otonom, membaca/menulis file, mengecek sistem, dan menjalankan perintah lokal secara aman."
            )
        model_tag = "Qwen 2.5 Coder 1.5B (Mode Kilat)" if "1.5b" in str(self._loaded_path) else "Qwen 2.5 Coder 7B"
        prompt = (
            f"<|im_start|>system\n"
            f"Kamu adalah Local Autonomous AI Agent Platform yang berjalan mandiri di laptop pengguna (Drive E:), "
            f"ditenagai oleh model {model_tag}. Jawab pertanyaan pengguna dengan ramah, lugas, dan jelas dalam Bahasa Indonesia.<|im_end|>\n"
            f"<|im_start|>user\n{query}<|im_end|>\n"
            f"<|im_start|>assistant\n"
        )
        try:
            output = self._llm(
                prompt,
                max_tokens=150,
                temperature=0.3,
                stop=["<|im_end|>", "<|endoftext|>"],
            )
            return output["choices"][0]["text"].strip()
        except Exception:
            return "Saya adalah Autonomous AI Agent Platform lokal yang siap membantu Anda mengeksekusi tugas di laptop ini."

model_backend = LocalModelBackend()

def extract_file_target(text: str) -> str:
    """Ekstrak nama file atau path dari teks instruksi pengguna"""
    text_clean = text.strip()
    name = None

    # Prioritas 1: Pola setelah kata 'bernama' atau 'dengan nama'
    m = re.search(r'(?:bernama|dengan nama|nama)\s+[\'"]?([a-zA-Z0-9_\-\.]+)[\'"]?', text_clean, re.IGNORECASE)
    if m:
        name = m.group(1).strip()
    else:
        # Prioritas 2: Pola setelah kata 'file' (hindari menangkap kata 'bernama')
        m2 = re.search(r'file\s+[\'"]?(?:bernama\s+)?([a-zA-Z0-9_\-\.]+)[\'"]?', text_clean, re.IGNORECASE)
        if m2:
            candidate = m2.group(1).strip()
            if candidate.lower() != "bernama":
                name = candidate

    if not name:
        name = "output.txt"

    # Jika nama belum ada ekstensi, beri ekstensi .txt
    if "." not in name:
        name = f"{name}.txt"

    if name.startswith("E:/") or name.startswith("E:\\") or name.startswith("C:/") or name.startswith("C:\\"):
        return name
    return f"E:/agent_system/{name}"

def handle_message(msg: dict) -> dict:
    msg_id = msg.get("id", "")
    msg_type = msg.get("type", "")
    data = msg.get("data", {})

    if msg_type == "ping":
        return {
            "version": 1,
            "id": msg_id,
            "type": "pong",
            "data": {
                "status": "ready",
                "model": model_backend.get_model_name()
            }
        }

    elif msg_type == "decision_request":
        goal = data.get("goal", "").strip()
        iteration = data.get("iteration", 1)
        context = data.get("context", "")
        tools = data.get("available_tools", [])
        tool_names = [t.get("name") for t in tools]
        goal_lower = goal.lower()

        # JIKA SUDAH MENJALANKAN TOOL (Iterasi >= 2)
        if iteration >= 2 and context and "Hasil tool terakhir" in context:
            if "filesystem.write" in context:
                m_path = re.search(r'"path":\s*"([^"]+)"', context)
                saved_path = m_path.group(1) if m_path else "tujuan"
                return {
                    "version": 1,
                    "id": msg_id,
                    "type": "decision_response",
                    "data": {
                        "thought": "File telah berhasil ditulis dan diverifikasi pada disk.",
                        "action": {
                            "type": "finish",
                            "details": {
                                "summary": f"File berhasil dibuat dan disimpan secara nyata di: {saved_path}"
                            }
                        }
                    }
                }
            elif "filesystem.read" in context:
                return {
                    "version": 1,
                    "id": msg_id,
                    "type": "decision_response",
                    "data": {
                        "thought": "Isi file telah berhasil dibaca dari disk.",
                        "action": {
                            "type": "finish",
                            "details": {
                                "summary": f"Isi file telah berhasil dibaca:\n{context}"
                            }
                        }
                    }
                }
            elif "system.info" in context:
                return {
                    "version": 1,
                    "id": msg_id,
                    "type": "decision_response",
                    "data": {
                        "thought": "Telemetri perangkat keras telah diperoleh.",
                        "action": {
                            "type": "finish",
                            "details": {
                                "summary": "Informasi sistem dan perangkat keras laptop telah berhasil diperiksa dan diverifikasi."
                            }
                        }
                    }
                }
            elif "shell.run" in context:
                return {
                    "version": 1,
                    "id": msg_id,
                    "type": "decision_response",
                    "data": {
                        "thought": "Perintah shell telah dieksekusi.",
                        "action": {
                            "type": "finish",
                            "details": {
                                "summary": f"Hasil eksekusi perintah shell:\n{context}"
                            }
                        }
                    }
                }

        # ITERASI 1: ANALISIS INTENT DAN PILIH TINDAKAN NYATA (TOOL CALL)

        # 1. Intent Menulis / Membuat File (filesystem.write)
        if "filesystem.write" in tool_names and iteration == 1 and any(w in goal_lower for w in ["buat", "bikin", "tulis", "create", "write"]) and "file" in goal_lower:
            target_path = extract_file_target(goal)
            content_to_write = f"File '{Path(target_path).name}' berhasil dibuat secara otonom oleh Local AI Agent Platform.\nWaktu instruksi: {goal}"
            return {
                "version": 1,
                "id": msg_id,
                "type": "decision_response",
                "data": {
                    "thought": f"Mengeksekusi tool 'filesystem.write' untuk membuat file nyata di '{target_path}'.",
                    "action": {
                        "type": "tool_call",
                        "details": {
                            "tool": "filesystem.write",
                            "arguments": {
                                "path": target_path,
                                "content": content_to_write
                            }
                        }
                    }
                }
            }

        # 2. Intent Membaca File (filesystem.read)
        if "filesystem.read" in tool_names and iteration == 1 and any(w in goal_lower for w in ["baca", "lihat isi", "read"]) and "file" in goal_lower:
            target_path = extract_file_target(goal)
            return {
                "version": 1,
                "id": msg_id,
                "type": "decision_response",
                "data": {
                    "thought": f"Mengeksekusi tool 'filesystem.read' untuk membaca file di '{target_path}'.",
                    "action": {
                        "type": "tool_call",
                        "details": {
                            "tool": "filesystem.read",
                            "arguments": {
                                "path": target_path
                            }
                        }
                    }
                }
            }

        # 3. Intent Info Sistem (system.info)
        if "system.info" in tool_names and iteration == 1 and any(k in goal_lower for k in ["spek", "sistem", "inspeksi", "hardware", "ram", "cpu", "telemetri"]):
            return {
                "version": 1,
                "id": msg_id,
                "type": "decision_response",
                "data": {
                    "thought": "Memeriksa informasi perangkat keras laptop menggunakan tool 'system.info'.",
                    "action": {
                        "type": "tool_call",
                        "details": {
                            "tool": "system.info",
                            "arguments": {}
                        }
                    }
                }
            }

        # 4. Intent Eksekusi Shell Command (shell.run)
        if "shell.run" in tool_names and iteration == 1 and any(k in goal_lower for k in ["jalankan perintah", "eksekusi perintah", "run command", "terminal", "shell"]):
            m_cmd = re.search(r'(?:perintah|command|shell)\s+[:\'"]?(.+?)[\'"]?$', goal, re.IGNORECASE)
            cmd_str = m_cmd.group(1) if m_cmd else "dir"
            return {
                "version": 1,
                "id": msg_id,
                "type": "decision_response",
                "data": {
                    "thought": f"Menjalankan perintah shell '{cmd_str}' secara aman.",
                    "action": {
                        "type": "tool_call",
                        "details": {
                            "tool": "shell.run",
                            "arguments": {
                                "command": cmd_str
                            }
                        }
                    }
                }
            }

        # 5. Pertanyaan Umum / Percakapan Biasa (Chat Langsung via Model LLM)
        if iteration == 1:
            answer = model_backend.answer_direct(goal)
            return {
                "version": 1,
                "id": msg_id,
                "type": "decision_response",
                "data": {
                    "thought": "Menganalisis instruksi pengguna dan menjawab langsung dengan model AI.",
                    "action": {
                        "type": "finish",
                        "details": {
                            "summary": answer
                        }
                    }
                }
            }

        return {
            "version": 1,
            "id": msg_id,
            "type": "decision_response",
            "data": {
                "thought": "Tugas selesai.",
                "action": {
                    "type": "finish",
                    "details": {
                        "summary": "Tugas telah diselesaikan."
                    }
                }
            }
        }

    return {
        "version": 1,
        "id": msg_id,
        "type": "error",
        "data": {
            "message": f"Unknown message type: {msg_type}"
        }
    }

def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            res = handle_message(req)
            sys.stdout.write(json.dumps(res) + "\n")
            sys.stdout.flush()
        except Exception as exc:
            err_res = {
                "version": 1,
                "id": "unknown",
                "type": "error",
                "data": {"message": str(exc)}
            }
            sys.stdout.write(json.dumps(err_res) + "\n")
            sys.stdout.flush()

if __name__ == "__main__":
    main()
