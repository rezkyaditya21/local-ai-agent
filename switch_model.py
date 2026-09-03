import sys
import re
from pathlib import Path

# Possible config locations
CONFIG_PATHS = [
    Path("C:/Users/rezky/Documents/agent/config.toml"),
    Path("E:/agent_system/config.toml")
]

# Model files
PATH_1_5B_C = Path("C:/Users/rezky/Documents/models/qwen2.5-coder-1.5b-instruct-q4_k_m.gguf")
PATH_1_5B_E = Path("E:/agent_system/models/qwen2.5-coder-1.5b-instruct-q4_k_m.gguf")

PATH_7B_C = Path("C:/Users/rezky/Documents/models/qwen2.5-coder-7b-instruct-q4_k_m.gguf")
PATH_7B_E = Path("E:/agent_system/models/qwen2.5-coder-7b-instruct-q4_k_m.gguf")

PATH_14B_E = Path("E:/agent_system/models/qwen2.5-coder-14b-instruct-q4_k_m.gguf")

def switch(target: str):
    new_path = ""
    label = ""

    if target in ["1.5b", "1.5", "fast", "kilat"]:
        if PATH_1_5B_C.exists():
            new_path = str(PATH_1_5B_C).replace("\\", "/")
        else:
            new_path = str(PATH_1_5B_E).replace("\\", "/")
        label = "Qwen 2.5 Coder 1.5B (Mode Kilat)"
    elif target in ["7b", "7", "standard", "akurat"]:
        if PATH_7B_C.exists():
            new_path = str(PATH_7B_C).replace("\\", "/")
        else:
            new_path = str(PATH_7B_E).replace("\\", "/")
        label = "Qwen 2.5 Coder 7B (Mode Standar)"
    elif target in ["14b", "14", "smart", "pintar", "genius"]:
        new_path = str(PATH_14B_E).replace("\\", "/")
        label = "Qwen 2.5 Coder 14B (Mode Super Pintar - Butuh Harddisk E)"
    else:
        print(f"Pilihan tidak dikenali: {target}. Gunakan '1.5b', '7b', atau '14b'.")
        return

    updated_count = 0
    for cfg in CONFIG_PATHS:
        if cfg.exists():
            text = cfg.read_text(encoding="utf-8")
            text = re.sub(r'model_path\s*=\s*"[^"]+"', f'model_path = "{new_path}"', text)
            cfg.write_text(text, encoding="utf-8")
            updated_count += 1

    print(f"Model aktif sekarang: {label}")
    print(f"Path model: {new_path} (Diperbarui di {updated_count} config)")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        switch(sys.argv[1].lower())
    else:
        print("Gunakan: switch_model.bat 1.5b | 7b | 14b")
