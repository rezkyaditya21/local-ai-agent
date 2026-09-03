"""
agent/core/prompting.py

Antigravity-Grade Agentic Prompting Engine for Local AI Agent.
Injects deep system awareness, Rust-powered high-speed tools, surgical file editing,
and autonomous self-healing execution loops into the LLM context.
"""

from __future__ import annotations

from typing import Any

from agent.core.evaluator import VerificationResult
from agent.models.schemas import ToolResult

_MAX_RESULT_CHARS = 2500

TOOL_CALL_INSTRUCTIONS = """\
Kamu adalah Antigravity-Grade Autonomous AI Engineering Assistant yang cerdas, proaktif, dan berkuasa penuh atas sistem lokal.
Kamu memiliki akses langsung ke sistem operasi Windows 11, terminal PowerShell/CMD, filesystem, mesin performa tinggi Rust Core, dan internet.

LINGKUNGAN SISTEM:
- OS: Windows 11 Pro 64-bit | Shell: PowerShell / CMD
- Hardware: Intel Core i5-8365U (4C/8T Turbo 4.10GHz) | RAM: 16 GB | Storage: SSD C: (System) & HDD E: (Media/Archive)
- Runtime: Python 3.11, Node.js v24, Git 2.50, Rust Native Engine

GAYA KOMUNIKASI & KERJA:
- Berbicaralah dalam Bahasa Indonesia yang luwes, santai, percaya diri, dan solutif layaknya senior engineer.
- Selalu berorientasi pada TINDAKAN NYATA (Action-Oriented). Jangan hanya memberikan saran teoritis jika kamu bisa langsung mengeksekusi atau membuatkannya untuk pengguna.
- Jika terjadi error pada perintah terminal atau kode, jangan menyerah: baca pesan error, analisis penyebabnya, perbaiki kodenya, dan uji ulang sampai benar-benar berhasil (Self-Healing).

PENGGUNAAN TOOL:
Untuk menjalankan tugas, gunakan format JSON tunggal atau terstruktur:
{"tool": "<nama_tool>", "params": {<parameter>}}

Daftar Tool Utama:
- Mesin Rust Core: {"tool": "rust_core", "params": {"operation": "system_telemetry"|"fast_scan"|"fast_grep", ...}}
- Editor Berkas Bedah: {"tool": "file_editor", "params": {"operation": "view"|"write"|"replace", "path": "...", ...}}
- Terminal Windows: {"tool": "shell", "params": {"command": "<perintah powershell/cmd>"}}
- Filesystem: {"tool": "filesystem", "params": {"operation": "read_file"|"write_file"|"list_dir", "path": "..."}}
- Pencarian Kode: {"tool": "code_search", "params": {"query": "..."}}
- Eksekusi Python: {"tool": "python_exec", "params": {"code": "..."}}
- Internet / Web Search: {"tool": "web_search", "params": {"query": "..."}}
- Git: {"tool": "git", "params": {"command": "status"|"diff"|"commit"|...}}

Aturan:
- Gunakan tool saat pengguna meminta tindakan rekayasa, file, pencarian, atau status sistem.
- Untuk obrolan biasa atau tanya-jawab umum, jawab langsung dengan teks santai tanpa format JSON.
"""

GOAL_AWARE_INSTRUCTIONS = """\
Kamu adalah Autonomous Local AI Agent berkemampuan penuh (Antigravity-Grade).
Tujuan utama kamu adalah menyelesaikan instruksi pengguna sampai 100% tuntas dan terverifikasi.

PRINSIP EKSEKUSI OTONOM:
1. Pahami akar masalah dan rancang langkah penyelesaian yang presisi.
2. Gunakan tool secara proaktif (buat file, jalankan skrip, uji coba, periksa sistem).
3. Selalu VERIFIKASI hasil eksekusi: baca output tool, pastikan tidak ada error, dan pastikan file/fitur bekerja sesuai harapan.
4. Jika menemui kegagalan/bug, lakukan iterasi: ubah pendekatan, perbaiki error, dan uji kembali hingga tuntas.
5. Laporkan hasil akhir kepada pengguna secara ringkas, jelas, dan ramah.
"""


def summarize_tool_results(results: list[ToolResult]) -> str:
    """Ringkas hasil tool untuk prompt iterasi berikutnya."""
    if not results:
        return "(belum ada hasil tool)"

    lines: list[str] = []
    for i, result in enumerate(results, start=1):
        status = "berhasil" if result.success else f"gagal: {result.error}"
        lines.append(f"{i}. {result.tool_name}: {status}")
        if result.data is not None:
            data_str = str(result.data)
            if len(data_str) > _MAX_RESULT_CHARS:
                data_str = data_str[:_MAX_RESULT_CHARS] + "... [dipotong]"
            lines.append(f"   Data: {data_str}")
    return "\n".join(lines)


def build_chat_prompt(
    instruction: str,
    tool_catalog: str = "",
    memory_text: str = "",
    skills_text: str = "",
    history_text: str = "",
    last_results_text: str = "",
    task_focus: str = "",
    **kwargs: Any,
) -> str:
    """Bangun prompt interaktif / chat dengan katalog tool dan konteks sistem."""
    sections: list[str] = [TOOL_CALL_INSTRUCTIONS]

    if memory_text:
        sections.append(f"KONTEKS MEMORI SISTEM:\n{memory_text}")

    if skills_text:
        sections.append(f"KEAHLIAN / SKILLS TERKAIT:\n{skills_text}")

    if tool_catalog:
        sections.append(f"KATALOG TOOL TERSEDIA:\n{tool_catalog}")

    if history_text:
        sections.append(f"RIWAYAT PERCAKAPAN:\n{history_text}")

    if last_results_text and last_results_text != "(belum ada hasil tool)":
        sections.append(f"HASIL EKSEKUSI TOOL TERAKHIR:\n{last_results_text}")

    if task_focus:
        sections.append(f"FOKUS TUGAS SAAT INI:\n{task_focus}")

    sections.append(f"PERMINTAAN PENGGUNA:\n{instruction}")
    return "\n\n".join(sections)


def build_task_prompt(
    goal: str,
    tool_catalog: str = "",
    iteration: int = 1,
    budget_summary: str = "",
    memory_text: str = "",
    capability_text: str = "",
    last_results: Any = None,
    last_eval: Any = None,
    subtasks_text: str = "",
    last_action: str = "",
    verification_feedback: str = "",
    last_results_text: str = "",
    **kwargs: Any,
) -> str:
    """Bangun prompt autonomous goal loop."""
    sections: list[str] = [
        GOAL_AWARE_INSTRUCTIONS,
        f"TUJUAN UTAMA: {goal}",
        f"ITERASI SAAT INI: {iteration}",
    ]

    if budget_summary:
        sections.append(f"SISA BUDGET EKSEKUSI: {budget_summary}")

    if capability_text:
        sections.append(f"KEMAMPUAN SISTEM:\n{capability_text}")

    if subtasks_text:
        sections.append(f"RENCANA SUBTASKS:\n{subtasks_text}")

    if memory_text:
        sections.append(f"KONTEKS MEMORI:\n{memory_text}")

    if tool_catalog:
        sections.append(f"KATALOG TOOL TERSEDIA:\n{tool_catalog}")

    if last_action:
        sections.append(f"TINDAKAN SEBELUMNYA:\n{last_action}")

    if last_results:
        sections.append(f"HASIL TOOL SEBELUMNYA:\n{summarize_tool_results(last_results)}")
    elif last_results_text and last_results_text != "(belum ada hasil tool)":
        sections.append(f"HASIL TOOL SEBELUMNYA:\n{last_results_text}")

    if verification_feedback or last_eval:
        sections.append(f"EVALUASI HASIL:\n{verification_feedback or last_eval}")

    sections.append("Tentukan tindakan terbaik berikutnya via format JSON tool atau jawab jika tujuan sudah tercapai.")
    return "\n\n".join(sections)


def build_memory_context(
    working: Any = None,
    task_history: Any = None,
    long_term: Any = None,
    project_knowledge: Any = None,
    self_knowledge: Any = None,
    knowledge: Any = None,
    **kwargs: Any,
) -> str:
    """Bangun ringkasan konteks memori secara aman untuk list atau dict."""
    parts: list[str] = []
    if working:
        if isinstance(working, list):
            parts.append("Working Memory: " + ", ".join(str(w.get("content", w) if isinstance(w, dict) else w)[:80] for w in working[:3]))
        else:
            parts.append(f"Working Memory: {str(working)[:120]}")
    if long_term:
        if isinstance(long_term, list):
            parts.append("Long-term Memory:\n" + "\n".join(f"- {str(m)[:100]}" for m in long_term[:5]))
        elif isinstance(long_term, dict):
            parts.append("Long-term Memory:\n" + "\n".join(f"- {k}: {str(v)[:100]}" for k, v in list(long_term.items())[:5]))
    pk = project_knowledge or knowledge
    if pk:
        if isinstance(pk, list):
            parts.append("Project Knowledge:\n" + "\n".join(f"- {str(k.get('content', k) if isinstance(k, dict) else k)[:100]}" for k in pk[:3]))
        elif isinstance(pk, dict):
            parts.append("Project Knowledge:\n" + "\n".join(f"- {k}: {str(v)[:100]}" for k, v in list(pk.items())[:5]))
    if self_knowledge:
        if isinstance(self_knowledge, dict):
            parts.append("Self Knowledge:\n" + "\n".join(f"- {k}: {str(v)[:100]}" for k, v in list(self_knowledge.items())[:5]))
        elif isinstance(self_knowledge, list):
            parts.append("Self Knowledge:\n" + "\n".join(f"- {str(s.get('content', s) if isinstance(s, dict) else s)[:100]}" for s in self_knowledge[:5]))
    return "\n".join(parts)
