"""
agent/tools/rust_core.py

Rust-Powered Native System Engine & Telemetry Tool for Local AI Agent.
Provides high-performance hardware telemetry, ultra-fast file scanning,
and ripgrep-grade code search via Rust binary with seamless native fallback.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
from pathlib import Path
from typing import Any

from agent.models.schemas import ToolResult

_RUST_BIN = Path(__file__).parent / "agent-rust-core.exe"


class RustCoreTool:
    """High-speed native system engine powered by Rust."""

    name: str = "rust_core"
    description: str = (
        "Mesin sistem berkecepatan tinggi berbasis Rust untuk telemetri perangkat keras "
        "(CPU, RAM, Disk, Proses), pemindaian pohon file kilat, dan pencarian kode regex secepat ripgrep."
    )
    input_schema: dict = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["system_telemetry", "fast_scan", "fast_grep"],
                "description": "Operasi yang ingin dijalankan (system_telemetry, fast_scan, fast_grep).",
            },
            "path": {
                "type": "string",
                "description": "Path direktori untuk pemindaian atau pencarian kode (default: current dir).",
                "default": ".",
            },
            "query": {
                "type": "string",
                "description": "Kata kunci atau pola regex untuk fast_grep.",
                "default": "",
            },
            "is_regex": {
                "type": "boolean",
                "description": "Apakah query diperlakukan sebagai regex (default: false).",
                "default": False,
            },
            "limit": {
                "type": "integer",
                "description": "Batas maksimum hasil (default: 100).",
                "default": 100,
            },
        },
        "required": ["operation"],
    }
    output_schema: dict = {
        "type": "object",
        "properties": {
            "engine": {"type": "string"},
            "data": {"type": "object"},
        },
    }

    async def run(self, params: dict) -> ToolResult:
        """Eksekusi tool sesuai ToolInterface."""
        return await self.execute(**params)

    async def execute(self, **kwargs: Any) -> ToolResult:
        """Eksekusi operasi Rust Core."""
        op = kwargs.get("operation")
        path = kwargs.get("path", ".")
        query = kwargs.get("query", "")
        is_regex = bool(kwargs.get("is_regex", False))
        limit = int(kwargs.get("limit", 100))

        # 1. Coba eksekusi biner Rust jika ada
        if _RUST_BIN.is_file():
            try:
                cmd = [_RUST_BIN.as_posix(), op, path]
                if op == "fast_grep":
                    cmd.extend([query, "1" if is_regex else "0", str(limit)])
                elif op == "fast_scan":
                    cmd.extend(["4", str(limit)])

                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                if proc.returncode == 0:
                    return ToolResult(
                        success=True,
                        data=proc.stdout.strip(),
                        tool_name=self.name,
                    )
            except Exception:
                pass

        # 2. Native High-Speed Fallback (Python / Win32 / psutil emulation)
        return self._native_fallback(op, path, query, is_regex, limit)

    def _native_fallback(self, op: str, path: str, query: str, is_regex: bool, limit: int) -> ToolResult:
        """High-speed native fallback implementation."""
        try:
            if op == "system_telemetry":
                import psutil

                cpu_pct = psutil.cpu_percent(interval=0.05)
                cpu_cores = psutil.cpu_percent(interval=None, percpu=True)
                freq = psutil.cpu_freq()

                mem = psutil.virtual_memory()
                total_mem_gb = round(mem.total / (1024**3), 2)
                used_mem_gb = round(mem.used / (1024**3), 2)
                free_mem_gb = round(mem.available / (1024**3), 2)

                disks = []
                for p in psutil.disk_partitions(all=False):
                    try:
                        usage = psutil.disk_usage(p.mountpoint)
                        disks.append({
                            "mount_point": p.mountpoint,
                            "fstype": p.fstype,
                            "total_gb": round(usage.total / (1024**3), 2),
                            "free_gb": round(usage.free / (1024**3), 2),
                            "percent_used": usage.percent,
                        })
                    except Exception:
                        continue

                top_procs = []
                for proc in sorted(psutil.process_iter(['pid', 'name', 'memory_percent', 'cpu_percent']),
                                  key=lambda p: p.info.get('memory_percent') or 0, reverse=True)[:8]:
                    top_procs.append({
                        "pid": proc.info['pid'],
                        "name": proc.info['name'],
                        "mem_percent": round(proc.info.get('memory_percent') or 0, 1),
                    })

                telemetry = {
                    "engine": "rust_core_hybrid",
                    "os": f"{platform.system()} {platform.release()}",
                    "hostname": platform.node(),
                    "cpu": {
                        "brand": platform.processor(),
                        "usage_total_percent": cpu_pct,
                        "cores_usage": cpu_cores,
                        "current_freq_mhz": freq.current if freq else None,
                    },
                    "memory": {
                        "total_gb": total_mem_gb,
                        "used_gb": used_mem_gb,
                        "free_gb": free_mem_gb,
                        "usage_percent": mem.percent,
                    },
                    "disks": disks,
                    "top_memory_processes": top_procs,
                }
                return ToolResult(
                    success=True,
                    data=json.dumps(telemetry, indent=2),
                    tool_name=self.name,
                )

            elif op == "fast_scan":
                target = Path(path).resolve()
                entries = []
                total_files = 0
                total_dirs = 0

                for root, dirs, files in os.walk(target):
                    total_dirs += len(dirs)
                    for f in files:
                        total_files += 1
                        if len(entries) < limit:
                            fp = Path(root) / f
                            entries.append({
                                "name": f,
                                "path": str(fp),
                                "size_bytes": fp.stat().st_size if fp.exists() else 0,
                            })

                result = {
                    "root": str(target),
                    "total_files": total_files,
                    "total_dirs": total_dirs,
                    "sample_entries": entries,
                }
                return ToolResult(
                    success=True,
                    data=json.dumps(result, indent=2),
                    tool_name=self.name,
                )

            elif op == "fast_grep":
                import re
                target = Path(path).resolve()
                pattern = re.compile(query if is_regex else re.escape(query), re.IGNORECASE)
                matches = []
                code_exts = {".py", ".rs", ".js", ".ts", ".php", ".html", ".css", ".json", ".toml", ".md", ".sql"}

                for root, dirs, files in os.walk(target):
                    dirs[:] = [d for d in dirs if d not in {"node_modules", ".git", "__pycache__", "target", ".venv"}]
                    for f in files:
                        fp = Path(root) / f
                        if fp.suffix.lower() in code_exts:
                            try:
                                with open(fp, "r", encoding="utf-8", errors="ignore") as file_obj:
                                    for line_num, line in enumerate(file_obj, 1):
                                        if pattern.search(line):
                                            matches.append({
                                                "file": str(fp),
                                                "line": line_num,
                                                "content": line.strip()[:200],
                                            })
                                            if len(matches) >= limit:
                                                break
                            except Exception:
                                pass
                        if len(matches) >= limit:
                            break
                    if len(matches) >= limit:
                        break

                return ToolResult(
                    success=True,
                    data=json.dumps({"query": query, "total_matches": len(matches), "matches": matches}, indent=2),
                    tool_name=self.name,
                )

            return ToolResult(success=False, data="", error=f"Unknown operation: {op}", tool_name=self.name)

        except Exception as exc:
            return ToolResult(success=False, data="", error=f"Error running rust_core operation: {exc}", tool_name=self.name)
