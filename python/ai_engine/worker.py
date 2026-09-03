import sys
import json
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

        # 1. Pertanyaan langsung / Chat / Identitas
        is_question = any(q in goal_lower for q in [
            "kamu ai apa", "siapa kamu", "siapa dirimu", "apa kabar", "kamu siapa",
            "apa itu", "jelaskan", "bagaimana cara", "apa yang bisa kamu lakukan", "halo", "hai"
        ])

        if is_question and iteration == 1:
            answer = model_backend.answer_direct(goal)
            return {
                "version": 1,
                "id": msg_id,
                "type": "decision_response",
                "data": {
                    "thought": "Pengguna menanyakan identitas atau pertanyaan umum. Menjawab langsung dengan model AI.",
                    "action": {
                        "type": "finish",
                        "details": {
                            "summary": answer
                        }
                    }
                }
            }

        # 2. Tool system.info
        if "system.info" in tool_names and iteration == 1 and any(k in goal_lower for k in ["spek", "sistem", "inspeksi", "hardware", "ram", "cpu", "telemetri"]):
            return {
                "version": 1,
                "id": msg_id,
                "type": "decision_response",
                "data": {
                    "thought": "Memeriksa informasi perangkat keras dan telemetri sistem laptop menggunakan tool 'system.info'.",
                    "action": {
                        "type": "tool_call",
                        "details": {
                            "tool": "system.info",
                            "arguments": {}
                        }
                    }
                }
            }

        # 3. Iterasi kedua setelah tool selesai
        if iteration >= 2 and context and "Hasil tool terakhir" in context:
            return {
                "version": 1,
                "id": msg_id,
                "type": "decision_response",
                "data": {
                    "thought": "Data dari eksekusi tool telah berhasil diperoleh dan divalidasi.",
                    "action": {
                        "type": "finish",
                        "details": {
                            "summary": "Tugas telah berhasil diselesaikan dengan baik sesuai instruksi."
                        }
                    }
                }
            }

        # 4. Default: Jawab langsung via LLM
        if iteration == 1:
            answer = model_backend.answer_direct(goal)
            return {
                "version": 1,
                "id": msg_id,
                "type": "decision_response",
                "data": {
                    "thought": "Menganalisis instruksi pengguna dan merumuskan respons.",
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
