"""
agent/core/credential_vault.py

Encrypted credential storage using Fernet symmetric encryption.

Design notes:
- Credentials are stored in a JSON file where each value is a Fernet-encrypted,
  base64-encoded string. The file is NOT readable as plaintext.
- A dedicated Fernet key file is stored separately with restrictive permissions
  (0o600 on POSIX). On first run the key is generated automatically.
- Decrypted values are NEVER logged, printed, or included in any string
  representation of this object. Only key names are exposed publicly.
- Requirements: 6.4, 10.5
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Final

from cryptography.fernet import Fernet, InvalidToken

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_KEY_FILENAME: Final[str] = "vault.key"
_VAULT_FILENAME: Final[str] = "vault.json"

# ---------------------------------------------------------------------------
# CredentialVault
# ---------------------------------------------------------------------------


class CredentialVault:
    """Encrypted credential storage backed by a JSON file.

    All credential *values* are encrypted with Fernet before being written
    to disk. Only key names are ever exposed in memory outside this class.

    Args:
        vault_path: Directory (or file path) for the vault.
            - If ``vault_path`` is a directory, the vault file is placed at
              ``<vault_path>/vault.json`` and the key file at
              ``<vault_path>/vault.key``.
            - If ``vault_path`` is a file path, that exact path is used as the
              vault file and ``<parent>/vault.key`` as the key file.
            Defaults to ``~/.config/local-ai-agent/`` when ``None``.

    Raises:
        PermissionError: If the key file or vault file cannot be read/written.
        cryptography.fernet.InvalidToken: If the vault file is corrupted.
    """

    def __init__(self, vault_path: Path | None = None) -> None:
        if vault_path is None:
            base_dir = Path.home() / ".config" / "local-ai-agent"
        elif vault_path.suffix == "":
            # Treat as a directory
            base_dir = vault_path
        else:
            # Treat as the vault file itself
            base_dir = vault_path.parent
            # Override the vault filename to the given filename
            self._vault_file = vault_path
            self._key_file = base_dir / _KEY_FILENAME
            base_dir.mkdir(parents=True, exist_ok=True)
            self._fernet = self._load_or_create_key(self._key_file)
            self._data: dict[str, str] = self._load_vault()
            return

        base_dir.mkdir(parents=True, exist_ok=True)
        self._vault_file = base_dir / _VAULT_FILENAME
        self._key_file = base_dir / _KEY_FILENAME
        self._fernet = self._load_or_create_key(self._key_file)
        self._data: dict[str, str] = self._load_vault()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def store(self, key: str, value: str) -> None:
        """Encrypt *value* and persist it under *key*.

        Args:
            key: Credential identifier (e.g. ``"openai_api_key"``).
            value: Plaintext credential value. This is encrypted immediately
                and the plaintext reference is discarded after this call.
        """
        if not key:
            raise ValueError("Credential key must not be empty.")
        # Encrypt and discard the plaintext value as soon as possible.
        encrypted: str = self._fernet.encrypt(value.encode()).decode()
        self._data[key] = encrypted
        self._save_vault()

    def retrieve(self, key: str) -> str:
        """Decrypt and return the credential stored under *key*.

        The decrypted value is returned ONLY to the caller and is never
        logged, printed, or stored in any attribute of this object.

        Args:
            key: Credential identifier.

        Returns:
            The plaintext credential value.

        Raises:
            KeyError: If *key* does not exist in the vault.
            cryptography.fernet.InvalidToken: If the stored token is corrupt
                or was encrypted with a different key.
        """
        if key not in self._data:
            raise KeyError(f"Credential '{key}' not found in vault.")
        # Decrypt in a local variable — never assign to self or log.
        return self._fernet.decrypt(self._data[key].encode()).decode()

    def delete(self, key: str) -> None:
        """Remove *key* from the vault.

        Args:
            key: Credential identifier.

        Raises:
            KeyError: If *key* does not exist in the vault.
        """
        if key not in self._data:
            raise KeyError(f"Credential '{key}' not found in vault.")
        del self._data[key]
        self._save_vault()

    def list_keys(self) -> list[str]:
        """Return all stored credential key names.

        Values are NEVER included in the returned list.

        Returns:
            Sorted list of key names.
        """
        return sorted(self._data.keys())

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load_or_create_key(key_file: Path) -> Fernet:
        """Load an existing Fernet key or generate a new one.

        The key file is created with mode 0o600 (owner read/write only)
        on POSIX systems. On Windows the file is still private by default
        because it lives under the user's home directory.

        Args:
            key_file: Path to the ``.key`` file.

        Returns:
            A ready-to-use :class:`~cryptography.fernet.Fernet` instance.
        """
        if key_file.exists():
            raw_key = key_file.read_bytes().strip()
        else:
            raw_key = Fernet.generate_key()
            key_file.write_bytes(raw_key)
            # Restrict permissions to owner-only on POSIX
            try:
                key_file.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0o600
            except (AttributeError, NotImplementedError, OSError):
                # chmod may not be fully supported on all platforms
                pass

        return Fernet(raw_key)

    def _load_vault(self) -> dict[str, str]:
        """Load the vault JSON file.

        Returns an empty dict if the file does not yet exist. The JSON file
        contains only encrypted (ciphertext) values — never plaintext.

        Returns:
            Mapping of key name → encrypted token string.

        Raises:
            ValueError: If the vault file exists but cannot be parsed as JSON.
        """
        if not self._vault_file.exists():
            return {}

        raw = self._vault_file.read_text(encoding="utf-8")
        try:
            data: dict = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Vault file '{self._vault_file}' is not valid JSON: {exc}"
            ) from exc

        if not isinstance(data, dict):
            raise ValueError(
                f"Vault file '{self._vault_file}' must contain a JSON object."
            )

        return {str(k): str(v) for k, v in data.items()}

    def _save_vault(self) -> None:
        """Persist the in-memory vault to disk.

        The written file contains ONLY encrypted values — no plaintext.
        """
        self._vault_file.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    # Safety: prevent accidental value leakage in repr/str
    # ------------------------------------------------------------------

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"CredentialVault("
            f"vault_file={str(self._vault_file)!r}, "
            f"keys={self.list_keys()!r}"
            f")"
        )

    def __str__(self) -> str:  # pragma: no cover
        return repr(self)


__all__ = ["CredentialVault"]
