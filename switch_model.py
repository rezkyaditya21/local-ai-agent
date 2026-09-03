import sys
from pathlib import Path

CONFIG = Path("E:/agent_system/config.toml")
PATH_1_5B = "E:/agent_system/models/qwen2.5-coder-1.5b-instruct-q4_k_m.gguf"
PATH_7B = "C:/Users/rezky/Documents/models/qwen2.5-coder-7b-instruct-q4_k_m.gguf"

def switch(target: str):
    if not CONFIG.exists():
        print("config.toml not found!")
        return

    text = CONFIG.read_text(encoding="utf-8")

    if target in ["1.5b", "1.5", "fast", "kilat"]:
        text = text.replace(PATH_7B, PATH_1_5B)
        CONFIG.write_text(text, encoding="utf-8")
        print("Model aktif sekarang: Qwen 2.5 Coder 1.5B (Mode Kilat)")
    elif target in ["7b", "7", "standard", "akurat"]:
        text = text.replace(PATH_1_5B, PATH_7B)
        CONFIG.write_text(text, encoding="utf-8")
        print("Model aktif sekarang: Qwen 2.5 Coder 7B (Mode Akurat / Standar)")
    else:
        print(f"Pilihan tidak dikenali: {target}. Gunakan '1.5b' atau '7b'.")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        switch(sys.argv[1].lower())
    else:
        print("Gunakan: switch_model.bat 1.5b atau switch_model.bat 7b")
