"""AES-256-GCM encryption for API keys. Encrypted keys stored on disk, decrypted in memory."""

from __future__ import annotations

import os
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

from cryptopilot.core.config import ROOT_DIR
from cryptopilot.core.exceptions import SecurityError

KEY_FILE = ROOT_DIR / "data" / "keys.enc"


def _derive_key(password: str, salt: bytes) -> bytes:
    """Derive a 32-byte AES-256 key from password + salt using PBKDF2."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=600_000,
    )
    return kdf.derive(password.encode("utf-8"))


class Encryptor:
    """Manages encrypted API credentials on disk."""

    def __init__(self, password: str, salt_str: str = "cryptopilot_salt") -> None:
        self._password = password
        self._salt = salt_str.encode("utf-8")
        self._key = _derive_key(password, self._salt)
        self._aesgcm = AESGCM(self._key)
        self._api_key: str | None = None
        self._api_secret: str | None = None

    def initialize(self, api_key: str, api_secret: str) -> None:
        """Encrypt and write credentials to disk. Called on first setup."""
        nonce = os.urandom(12)
        plaintext = f"{api_key}\n{api_secret}".encode("utf-8")
        ciphertext = self._aesgcm.encrypt(nonce, plaintext, None)
        KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
        KEY_FILE.write_bytes(nonce + ciphertext)
        self._api_key = api_key
        self._api_secret = api_secret

    def load(self) -> None:
        """Decrypt credentials from disk into memory."""
        if not KEY_FILE.exists():
            raise SecurityError(
                f"Key file not found at {KEY_FILE}. "
                "Set BINANCE_API_KEY and BINANCE_API_SECRET in .env, "
                "then run with --encrypt-keys once."
            )

        data = KEY_FILE.read_bytes()
        nonce = data[:12]
        ciphertext = data[12:]

        try:
            plaintext = self._aesgcm.decrypt(nonce, ciphertext, None).decode("utf-8")
        except Exception as exc:
            raise SecurityError(
                "Failed to decrypt API keys. Wrong password or corrupted key file."
            ) from exc

        parts = plaintext.split("\n", 1)
        if len(parts) != 2:
            raise SecurityError("Corrupted key file: invalid format after decryption.")

        self._api_key, self._api_secret = parts

    def get_api_key(self) -> str:
        if self._api_key is None:
            raise SecurityError("Keys not loaded. Call load() first.")
        return self._api_key

    def get_api_secret(self) -> str:
        if self._api_secret is None:
            raise SecurityError("Keys not loaded. Call load() first.")
        return self._api_secret
