import sys
import re
from pathlib import Path

CONFIG = Path("E:/agent_system/config.toml")
PATH_1_5B = "E:/agent_system/models/qwen2.5-coder-1.5b-instruct-q4_k_m.gguf"
PATH_7B = "C:/Users/rezky/Documents/models/qwen2.5-coder-7b-instruct-q4_k_m.gguf"
PATH_14B = "E:/agent_system/models/qwen2.5-coder-14b-instruct-q4_k_m.gguf"

def switch(target: str):
    if not CONFIG.exists():
        print("config.toml not found!")
        return

    text = CONFIG.read_text(encoding="utf-8")

    if target in ["1.5b", "1.5", "fast", "kilat"]:
        new_path = PATH_1_5B
        label = "Qwen 2.5 Coder 1.5B (Mode Kilat)"
    elif target in ["7b", "7", "standard", "akurat"]:
        new_path = PATH_7B
        label = "Qwen 2.5 Coder 7B (Mode Standar / Akurat)"
    elif target in ["14b", "14", "smart", "pintar", "genius"]:
        new_path = PATH_14B
        label = "Qwen 2.5 Coder 14B (Mode Super Pintar)"
    else:
        print(f"Pilihan tidak dikenali: {target}. Gunakan '1.5b', '7b', atau '14b'.")
        return

    text = re.sub(r'model_path\s*=\s*"[^"]+"', f'model_path = "{new_path}"', text)
    CONFIG.write_text(text, encoding="utf-8")
    print(f"Model aktif sekarang: {label}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        switch(sys.argv[1].lower())
    else:
        print("Gunakan: switch_model.bat 1.5b | 7b | 14b")
