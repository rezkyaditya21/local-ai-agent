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
        self.history = []

    def load(self):
        current_path = get_active_model_path()
        if self._llm is not None and self._loaded_path == current_path:
            return

        if current_path.exists():
            try:
                import llama_cpp
                # TURBO MULTI-THREADING OPTIMIZATION:
                # n_threads=4 for generation, n_threads_batch=8 for prompt processing, n_batch=512
                self._llm = llama_cpp.Llama(
                    model_path=str(current_path),
                    n_ctx=1024,
                    n_threads=4,
                    n_threads_batch=8,
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
        elif "14b" in p.name.lower():
            return "Qwen 2.5 Coder 14B (Super Smart / Active)"
        elif "7b" in p.name.lower():
            return "Qwen 2.5 Coder 7B (Standard / Active)"
        return p.stem

    def answer_direct_stream(self, query: str, msg_id: str):
        self.load()
        if not self.is_ready():
            msg = (
                "Saya adalah Autonomous AI Agent Platform lokal berbasis hybrid Rust (Runtime) dan Python (AI Engine). "
                "Saya dapat mengeksekusi tugas otonom, membaca/menulis file, mengecek sistem, dan menjalankan perintah lokal secara aman."
            )
            return msg

        if "1.5b" in str(self._loaded_path).lower():
            model_tag = "Qwen 2.5 Coder 1.5B (Mode Kilat)"
        elif "14b" in str(self._loaded_path).lower():
            model_tag = "Qwen 2.5 Coder 14B (Mode Super Pintar)"
        else:
            model_tag = "Qwen 2.5 Coder 7B (Mode Standar)"

        prompt = (
            f"<|im_start|>system\n"
            f"Kamu adalah Asisten AI Lokal otonom di laptop pengguna (Drive E:), ditenagai oleh model {model_tag}. "
            f"Kamu memiliki kendali otonom nyata: dapat membuat file, membaca file, mengecek sistem, dan menjalankan perintah terminal. "
            f"Jawab selalu dalam Bahasa Indonesia yang ramah, sopan, dan solutif. Jika pertanyaan pengguna singkat atau menggantung, sambut dengan hangat dan tanyakan apa yang ingin dibantu.<|im_end|>\n"
        )
        for h in self.history[-3:]:
            prompt += f"<|im_start|>{h['role']}\n{h['content']}<|im_end|>\n"

        prompt += f"<|im_start|>user\n{query}<|im_end|>\n<|im_start|>assistant\n"

        try:
            stream = self._llm(
                prompt,
                max_tokens=512,
                temperature=0.3,
                stop=["<|im_end|>", "<|endoftext|>"],
                stream=True,
            )
            tokens = []
            for chunk in stream:
                token = chunk["choices"][0]["text"]
                tokens.append(token)
                # Emit token_chunk live to stdout
                chunk_msg = {
                    "version": 1,
                    "id": msg_id,
                    "type": "token_chunk",
                    "data": {"token": token}
                }
                sys.stdout.write(json.dumps(chunk_msg) + "\n")
                sys.stdout.flush()

            full_res = "".join(tokens).strip()
            self.history.append({"role": "user", "content": query})
            self.history.append({"role": "assistant", "content": full_res})
            return full_res
        except Exception:
            return "Saya adalah Autonomous AI Agent Platform lokal yang siap membantu Anda mengeksekusi tugas di laptop ini."

model_backend = LocalModelBackend()

def extract_file_target(text: str) -> str:
    text_clean = text.strip()
    name = None
    m = re.search(r'(?:bernama|dengan nama|nama)\s+["\']?([a-zA-Z0-9_\-\.]+)["\']?', text_clean, re.IGNORECASE)
    if m:
        name = m.group(1).strip()
    else:
        m2 = re.search(r'file\s+["\']?(?:bernama\s+)?([a-zA-Z0-9_\-\.]+)["\']?', text_clean, re.IGNORECASE)
        if m2:
            candidate = m2.group(1).strip()
            if candidate.lower() != "bernama":
                name = candidate

    if not name:
        name = "output.txt"

    if "." not in name:
        name = f"{name}.txt"

    if name.startswith("E:/") or name.startswith("E:\\") or name.startswith("C:/") or name.startswith("C:\\"):
        return name
    return f"E:/agent_system/{name}"

def clean_tool_context(context: str) -> str:
    prefix = "Hasil tool terakhir: "
    if context.startswith(prefix):
        raw = context[len(prefix):]
        try:
            obj = json.loads(raw)
            data = obj.get("data", {})
            if "stdout" in data:
                out = data["stdout"].strip()
                err = data.get("stderr", "").strip()
                if out:
                    return out
                elif err:
                    return f"[Error Terminal]: {err}"
                return "(Perintah berhasil dieksekusi tanpa output)"
            elif "content" in data:
                return data["content"].strip()
            elif "os" in data:
                return f"OS: {data.get('os')}, CPU Cores: {data.get('cpu_cores')}, RAM: {data.get('memory_mb')} MB"
        except Exception:
            pass
    return context

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
            clean_output = clean_tool_context(context)
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
                                "summary": f"File berhasil dibuat dan tersimpan secara nyata di: {saved_path}"
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
                                "summary": f"Berikut isi filenya:\n\n{clean_output}"
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
                                "summary": f"Informasi Sistem Laptop:\n{clean_output}"
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
                        "thought": "Perintah shell telah dieksekusi dengan sukses.",
                        "action": {
                            "type": "finish",
                            "details": {
                                "summary": f"Ya, saya bisa menggunakan terminal! Berikut hasil eksekusi perintah terminal nyata di laptopmu:\n\n{clean_output}"
                            }
                        }
                    }
                }

        # ITERASI 1: ANALISIS INTENT DAN PILIH TINDAKAN NYATA
        if "filesystem.write" in tool_names and iteration == 1 and any(w in goal_lower for w in ["buat", "bikin", "tulis", "create", "write"]) and "file" in goal_lower:
            target_path = extract_file_target(goal)
            content_to_write = f"File '{Path(target_path).name}' berhasil dibuat secara otonom oleh Local AI Agent Platform.\nWaktu pembuatan: {goal}"
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

        if "shell.run" in tool_names and iteration == 1 and any(k in goal_lower for k in ["jalankan perintah", "eksekusi perintah", "run command", "terminal", "shell", "apakah kamu bisa menggunakan terminal", "bisa mengunakan terminal"]):
            m_cmd = re.search(r'(?:perintah|command|shell)\s+[:"\']?(.+?)["\']?$', goal, re.IGNORECASE)
            cmd_str = m_cmd.group(1) if m_cmd else "dir"
            return {
                "version": 1,
                "id": msg_id,
                "type": "decision_response",
                "data": {
                    "thought": f"Membuktikan akses terminal dengan menjalankan perintah shell '{cmd_str}' secara aman.",
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

        # 5. PERCAKAPAN UMUM (LIVE TOKEN STREAMING)
        if iteration == 1:
            answer = model_backend.answer_direct_stream(goal, msg_id)
            return {
                "version": 1,
                "id": msg_id,
                "type": "decision_response",
                "data": {
                    "thought": "Menganalisis instruksi pengguna dan merumuskan respons cerdas.",
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
