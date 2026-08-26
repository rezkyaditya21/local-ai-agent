"""
agent/core/blocklist.py

Modul blocklist untuk membatasi akses Agent ke path file, perintah shell,
atau domain tertentu.

Format file blocklist (teks biasa):
    # Ini adalah komentar
    file_path:/etc/passwd
    file_path:/home/user/secrets*
    command:rm -rf
    command:shutdown
    domain:malicious.example.com

Aturan matching:
    - FILE_PATH : exact match atau glob (fnmatch) terhadap value
    - COMMAND   : substring match (case-insensitive) terhadap value
    - DOMAIN    : substring match (case-insensitive) terhadap value

Requirements: 10.7, 10.8
"""

from __future__ import annotations

import fnmatch
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class BlocklistEntryType(Enum):
    """Tipe entri yang didukung dalam blocklist."""

    FILE_PATH = "file_path"
    COMMAND = "command"
    DOMAIN = "domain"


@dataclass
class BlocklistEntry:
    """Satu entri dalam blocklist.

    Attributes:
        entry_type: Tipe entri (FILE_PATH, COMMAND, atau DOMAIN).
        pattern:    Pola matching — exact/glob untuk FILE_PATH,
                    substring untuk COMMAND dan DOMAIN.
    """

    entry_type: BlocklistEntryType
    pattern: str


class Blocklist:
    """Mengelola daftar larangan (blocklist) untuk path file, perintah, dan domain.

    Dapat diinisialisasi dengan path file blocklist opsional. Jika file tidak
    ada, blocklist dimulai dalam keadaan kosong (graceful degradation).

    Args:
        blocklist_path: Path opsional ke file blocklist. Jika ``None`` atau
                        file tidak ditemukan, blocklist dimulai kosong.
    """

    def __init__(self, blocklist_path: str | None = None) -> None:
        self._entries: list[BlocklistEntry] = []

        if blocklist_path is not None:
            path = Path(blocklist_path)
            if path.exists() and path.is_file():
                self.load_from_file(blocklist_path)
            else:
                logger.debug(
                    "File blocklist '%s' tidak ditemukan; memulai dengan blocklist kosong.",
                    blocklist_path,
                )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_blocked(self, entry_type: BlocklistEntryType, value: str) -> bool:
        """Periksa apakah *value* diblokir untuk tipe entri yang diberikan.

        Aturan matching:
        - ``FILE_PATH``: exact match atau glob (fnmatch) — case-sensitive di
          platform Unix, case-insensitive di Windows (mengikuti perilaku
          ``fnmatch`` bawaan).
        - ``COMMAND``:   substring match, case-insensitive.
        - ``DOMAIN``:    substring match, case-insensitive.

        Args:
            entry_type: Tipe operasi yang akan diperiksa.
            value:      Nilai yang akan dicocokkan dengan entri blocklist.

        Returns:
            ``True`` jika *value* cocok dengan setidaknya satu pola dalam
            blocklist untuk tipe yang diberikan; ``False`` sebaliknya.
        """
        for entry in self._entries:
            if entry.entry_type != entry_type:
                continue

            if entry_type == BlocklistEntryType.FILE_PATH:
                # Exact match ATAU glob match
                if value == entry.pattern or fnmatch.fnmatch(value, entry.pattern):
                    return True
            else:
                # COMMAND dan DOMAIN: substring match, case-insensitive
                if entry.pattern.lower() in value.lower():
                    return True

        return False

    def load_from_file(self, path: str) -> None:
        """Muat entri blocklist dari file teks.

        Format setiap baris: ``type:pattern``
        - Baris kosong dan baris yang diawali ``#`` diabaikan.
        - Tipe yang tidak dikenali menghasilkan peringatan log dan dilewati.

        Args:
            path: Path ke file blocklist.

        Raises:
            FileNotFoundError: Jika file di *path* tidak ditemukan.
            OSError:           Jika file tidak dapat dibaca.
        """
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"File blocklist tidak ditemukan: '{path}'")

        loaded = 0
        skipped = 0

        with file_path.open(encoding="utf-8") as fh:
            for lineno, raw_line in enumerate(fh, start=1):
                line = raw_line.strip()

                # Abaikan komentar dan baris kosong
                if not line or line.startswith("#"):
                    continue

                # Pisahkan tipe dan pola pada pemisah pertama ':'
                if ":" not in line:
                    logger.warning(
                        "Blocklist '%s' baris %d: format tidak valid (tidak ada ':') — dilewati: %r",
                        path,
                        lineno,
                        line,
                    )
                    skipped += 1
                    continue

                type_str, _, pattern = line.partition(":")
                type_str = type_str.strip().lower()
                pattern = pattern.strip()

                # Validasi tipe
                type_map = {t.value: t for t in BlocklistEntryType}
                if type_str not in type_map:
                    logger.warning(
                        "Blocklist '%s' baris %d: tipe tidak dikenal '%s' — dilewati.",
                        path,
                        lineno,
                        type_str,
                    )
                    skipped += 1
                    continue

                if not pattern:
                    logger.warning(
                        "Blocklist '%s' baris %d: pola kosong — dilewati.",
                        path,
                        lineno,
                    )
                    skipped += 1
                    continue

                self._entries.append(
                    BlocklistEntry(entry_type=type_map[type_str], pattern=pattern)
                )
                loaded += 1

        logger.debug(
            "Blocklist dimuat dari '%s': %d entri dimuat, %d dilewati.",
            path,
            loaded,
            skipped,
        )

    def add_entry(self, entry: BlocklistEntry) -> None:
        """Tambahkan satu entri ke blocklist secara dinamis.

        Entri duplikat (tipe dan pola identik) diizinkan tetapi tidak
        memberikan efek tambahan karena ``is_blocked`` mengembalikan ``True``
        pada pencocokan pertama yang ditemukan.

        Args:
            entry: Entri blocklist yang akan ditambahkan.
        """
        self._entries.append(entry)

    # ------------------------------------------------------------------
    # Informational helpers (tidak dipersyaratkan oleh desain, berguna
    # untuk debugging dan testing)
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        """Kembalikan jumlah entri dalam blocklist."""
        return len(self._entries)

    def __repr__(self) -> str:
        return f"Blocklist(entries={len(self._entries)})"
