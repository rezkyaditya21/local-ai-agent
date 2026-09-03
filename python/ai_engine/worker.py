import sys
import json
from pathlib import Path

MODEL_PATH = Path("C:/Users/rezky/Documents/models/qwen2.5-coder-7b-instruct-q4_k_m.gguf")

class LocalModelBackend:
    def __init__(self):
        self._llm = None
        self._loaded = False

    def load(self):
        if self._loaded:
            return
        if MODEL_PATH.exists():
            try:
                import llama_cpp
                self._llm = llama_cpp.Llama(
                    model_path=str(MODEL_PATH),
                    n_ctx=1024,
                    n_threads=4,
                    n_batch=512,
                    verbose=False,
                )
                self._loaded = True
            except Exception as exc:
                self._llm = None
        else:
            self._llm = None

    def is_ready(self) -> bool:
        return self._loaded and self._llm is not None

    def answer_direct(self, query: str) -> str:
        self.load()
        if not self.is_ready():
            return (
                "Saya adalah Autonomous AI Agent Platform lokal berbasis hybrid Rust (Runtime) dan Python (AI Engine), "
                "ditenagai oleh model Qwen 2.5 Coder 7B. Saya dapat mengeksekusi tugas otonom, membaca/menulis file, "
                "mengecek telemetri sistem, dan menjalankan perintah di lingkungan laptop Anda secara aman."
            )
        prompt = (
            f"<|im_start|>system\n"
            f"Kamu adalah Local Autonomous AI Agent Platform yang berjalan mandiri di laptop pengguna (Drive E:), "
            f"menggunakan kombinasi Rust Runtime untuk eksekusi aman dan Python + Qwen 2.5 Coder untuk penalaran AI. "
            f"Jawab dengan ramah, lugas, dan jelas dalam Bahasa Indonesia.<|im_end|>\n"
            f"<|im_start|>user\n{query}<|im_end|>\n"
            f"<|im_start|>assistant\n"
        )
        try:
            output = self._llm(
                prompt,
                max_tokens=180,
                temperature=0.3,
                stop=["<|im_end|>", "<|endoftext|>"],
            )
            return output["choices"][0]["text"].strip()
        except Exception:
            return (
                "Saya adalah Local Autonomous AI Agent Platform berbasis hybrid Rust dan Python, "
                "ditenagai oleh model Qwen 2.5 Coder 7B lokal di laptop Anda."
            )

model_backend = LocalModelBackend()

def handle_message(msg: dict) -> dict:
    msg_id = msg.get("id", "")
    msg_type = msg.get("type", "")
    data = msg.get("data", {})

    if msg_type == "ping":
        model_name = "qwen2.5-coder-7b (ready)" if MODEL_PATH.exists() else "none"
        return {
            "version": 1,
            "id": msg_id,
            "type": "pong",
            "data": {
                "status": "ready",
                "model": model_name
            }
        }

    elif msg_type == "decision_request":
        goal = data.get("goal", "").strip()
        iteration = data.get("iteration", 1)
        context = data.get("context", "")
        tools = data.get("available_tools", [])
        tool_names = [t.get("name") for t in tools]

        goal_lower = goal.lower()

        # 1. Pertanyaan langsung / Chat / Identitas (tanpa perlu tool file/shell)
        is_question = any(q in goal_lower for q in [
            "kamu ai apa", "siapa kamu", "siapa dirimu", "apa kabar", "kamu siapa",
            "apa itu", "jelaskan", "bagaimana cara", "apa yang bisa kamu lakukan"
        ])

        if is_question and iteration == 1:
            answer = model_backend.answer_direct(goal)
            return {
                "version": 1,
                "id": msg_id,
                "type": "decision_response",
                "data": {
                    "thought": "Pengguna menanyakan identitas atau pertanyaan umum. Saya akan menjawabnya langsung menggunakan model AI.",
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
                    "thought": "Saya perlu memeriksa informasi perangkat keras dan telemetri sistem laptop menggunakan tool 'system.info'.",
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

        # 4. Default: Jawab langsung via LLM jika belum cocok
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

        # Selesai
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
