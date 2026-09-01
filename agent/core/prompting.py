"""
agent/core/prompting.py

Membangun prompt agent: katalog tool, instruksi pemanggilan JSON, dan konteks memori.
"""

from __future__ import annotations

from typing import Any

from agent.core.evaluator import VerificationResult
from agent.models.schemas import ToolResult

_MAX_RESULT_CHARS = 2000

TOOL_CALL_INSTRUCTIONS = """\
Kamu adalah AI Assistant yang cerdas, ramah, komunikatif, dan memiliki akses penuh ke sistem lokal, terminal/shell, filesystem, dan internet.

GAYA BAHASA & KOMUNIKASI:
- Berbicaralah dalam Bahasa Indonesia yang luwes, santai, dan alami seperti rekan kerja/partner diskusi yang asik dan solutif.
- Hindari bahasa kaku, baku berlebihan, atau kalimat template robotik.
- Sesuaikan nada bicara dengan pengguna: jika pengguna menyapa santai ("hai", "halo", "bro", "p"), balas dengan ramah dan santai.
- Jawab secara jelas, to-the-point, dan mudah dipahami.

PENGGUNAAN TOOL:
Untuk menjalankan tugas sistem atau mencari informasi, panggil tool via format JSON:
{"tool": "<nama_tool>", "params": {<parameter>}}

Daftar Tool Utama:
- Terminal / Shell: {"tool": "shell", "params": {"command": "<perintah terminal>"}}
- Internet / Web Search: {"tool": "web_search", "params": {"query": "<kata kunci>"}}
- HTTP API / Fetch URL: {"tool": "http_api", "params": {"method": "GET", "url": "<url>"}}
- Filesystem: {"tool": "filesystem", "params": {"operation": "read_file"|"write_file"|"list_dir", "path": "<path>"}}
- Pencarian Kode: {"tool": "code_search", "params": {"query": "<simbol/teks>"}}
- Git: {"tool": "git", "params": {"command": "<subcommand git>"}}

Aturan:
- Gunakan tool HANYA jika pengguna meminta tindakan yang memerlukan eksekusi terminal, akses internet, atau manipulasi file.
- Untuk obrolan biasa atau pertanyaan umum tanpa tool, langsung jawab dengan teks santai tanpa JSON tool.
- Jangan mengarang hasil eksekusi; ceritakan hasil tool yang sebenarnya dengan bahasa yang enak dibaca.
"""

GOAL_AWARE_INSTRUCTIONS = """\
Kamu adalah Autonomous Local AI Agent yang cerdas dan solutif, dengan akses penuh ke terminal lokal, filesystem, dan internet.
Tujuan kamu adalah menyelesaikan tugas yang diminta pengguna secara tuntas dan berkualitas.

GAYA BAHASA:
- Komunikatif, percaya diri, ramah, dan solutif dalam Bahasa Indonesia yang alami.

ATURAN UTAMA:
1. Gunakan tool dengan format JSON:
   {"tool": "<nama_tool>", "params": {<param>}}
2. Kamu memiliki akses terminal via `shell` dan internet via `web_search` / `http_api` / `browser`.
3. Kamu harus MEMVERIFIKASI bahwa tujuan benar-benar tercapai sebelum mengatakan selesai.
4. Keberhasilan eksekusi tool BUKAN bukti tujuan tercapai; verifikasi output, tes, dan status file.
5. Jika ada error atau kendala, analisis penyebabnya dan temukan solusi terbaik.
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
    tool_catalog: str,
    memory_text: str = "",
    skills_text: str = "",
) -> str:
    """Prompt satu-siklus (mode /chat) dengan katalog tool, memori, dan skill relevan."""
    parts = [
        TOOL_CALL_INSTRUCTIONS,
        "",
        "Katalog tool:",
        tool_catalog or "(tidak ada tool aktif)",
    ]
    if skills_text.strip():
        parts.extend(["", skills_text.strip()])
    if memory_text.strip():
        parts.extend(["", "Memori relevan:", memory_text.strip()])
    parts.extend(["", "Instruksi pengguna:", instruction])
    return "\n".join(parts)


def build_task_prompt(
    *,
    goal: str,
    tool_catalog: str,
    iteration: int,
    budget_summary: str,
    memory_text: str = "",
    skills_text: str = "",
    capability_text: str = "",
    last_results: list[ToolResult] | None = None,
    last_eval: VerificationResult | None = None,
    extra: str = "",
) -> str:
    """Prompt closed-loop: goal, katalog, memori, skill, dan hasil iterasi sebelumnya."""
    parts = [
        GOAL_AWARE_INSTRUCTIONS,
        "",
        f"Tujuan: {goal}",
        f"Iterasi: {iteration}",
        f"Anggaran: {budget_summary}",
        "",
        "Katalog tool:",
        tool_catalog or "(tidak ada tool aktif)",
    ]
    if skills_text.strip():
        parts.extend(["", skills_text.strip()])
    if capability_text.strip():
        parts.extend(["", "Kemampuan system:", capability_text.strip()])
    if memory_text.strip():
        parts.extend(["", "Memori relevan:", memory_text.strip()])
    if last_results:
        parts.extend(["", "Hasil tool iterasi sebelumnya:", summarize_tool_results(last_results)])
    if last_eval is not None:
        status = "langkah sehat" if last_eval.is_verified else "ada masalah"
        parts.append(f"Evaluasi langkah: {status} (confidence {last_eval.confidence_score:.2f})")
        if last_eval.failure_reasons:
            parts.append("Alasan: " + "; ".join(last_eval.failure_reasons))
        if last_eval.evidence:
            parts.append("Bukti: " + "; ".join(last_eval.evidence[:5]))
    if extra.strip():
        parts.extend(["", extra.strip()])
    parts.extend(
        [
            "",
            "Lanjutkan pekerjaan menuju tujuan. Jika tujuan sudah terpenuhi berdasarkan "
            "bukti di atas, berikan jawaban akhir tanpa JSON tool. "
            "Jika belum, gunakan tool yang sesuai untuk melanjutkan.",
        ]
    )
    return "\n".join(parts)


def build_goal_verification_prompt(
    *,
    goal: str,
    tool_results_summary: str,
    iteration: int,
) -> str:
    """Bangun prompt untuk memverifikasi goal via LLM."""
    return (
        f"Verifikasi apakah tujuan berikut benar-benar tercapai:\n\n"
        f"Tujuan: {goal}\n\n"
        f"Hasil eksekusi:\n{tool_results_summary}\n\n"
        f"Analisis secara objektif:\n"
        f"1. Apakah semua aspek tujuan sudah terpenuhi?\n"
        f"2. Apakah ada bukti konkret (test lulus, file berubah, error hilang)?\n"
        f"3. Jika belum, langkah apa yang masih diperlukan?\n\n"
        f"Balas dalam format JSON:\n"
        f'{{"status": "completed" atau "in_progress" atau "failed", '
        f'"confidence": 0.0-1.0, '
        f'"evidence": ["bukti1", "bukti2"], '
        f'"failure_reasons": ["alasan1"], '
        f'"should_replan": true/false, '
        f'"next_steps": ["langkah1"]}}'
    )


def format_memory_entries(entries: list[Any]) -> str:
    """Format entri long-term memory menjadi teks prompt."""
    if not entries:
        return ""
    lines: list[str] = []
    for entry in entries:
        key = getattr(entry, "key", "")
        content = getattr(entry, "content", "")
        category = getattr(entry, "category", "")
        lines.append(f"- [{category}] {key}: {content}")
    return "\n".join(lines)


def build_memory_context(
    working: dict[str, Any] | None = None,
    task_history: list[dict[str, Any]] | None = None,
    long_term: list[Any] | None = None,
    project_knowledge: dict[str, Any] | None = None,
    self_knowledge: dict[str, Any] | None = None,
) -> str:
    """Bangun context string dari semua layer memori untuk disuntikkan ke prompt."""
    parts: list[str] = []

    if working:
        parts.append("Working Memory:")
        for k, v in working.items():
            parts.append(f"  {k}: {str(v)[:200]}")

    if task_history:
        parts.append("Riwayat Tugas:")
        for item in task_history[-5:]:
            parts.append(f"  - {item.get('goal', '')}: {item.get('status', '')}")

    if long_term:
        parts.append("Pengetahuan Long-Term:")
        for entry in long_term[:5]:
            key = getattr(entry, "key", "")
            content = getattr(entry, "content", "")
            parts.append(f"  - {key}: {content[:150]}")

    if project_knowledge:
        parts.append("Pengetahuan Proyek:")
        for k, v in project_knowledge.items():
            parts.append(f"  - {k}: {str(v)[:150]}")

    if self_knowledge:
        failures = self_knowledge.get("tool_failure_patterns", {})
        strategies = self_knowledge.get("successful_strategies", [])
        if failures:
            parts.append("Tool Failure Patterns:")
            for tool, count in failures.items():
                parts.append(f"  - {tool}: {count} kegagalan")
        if strategies:
            parts.append("Strategi Sukses:")
            for s in strategies[-3:]:
                parts.append(f"  - {s.get('strategy', '')[:100]}")

    return "\n".join(parts) if parts else ""
