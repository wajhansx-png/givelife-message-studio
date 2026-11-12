"""Authenticated encryption for SQLite state values and portable backups.

The storage key is independent of the login key. No key is generated implicitly:
operators must preserve it separately from the database before enabling encryption.
"""

import base64
import hashlib
import json
import os

MARKER = "givelife-encrypted-v1"


class ValueCipher:
    def __init__(self):
        secret = os.environ.get("GIVELIFE_STORAGE_KEY", "")
        if secret and len(secret.encode()) < 32:
            raise ValueError(
                "GIVELIFE_STORAGE_KEY must contain at least 32 bytes of random secret material."
            )
        self.key = (
            hashlib.sha256(b"givelife-state-v1\0" + secret.encode()).digest() if secret else None
        )

    def encrypted(self, raw):
        try:
            return isinstance(json.loads(raw), dict) and json.loads(raw).get("format") == MARKER
        except (ValueError, TypeError):
            return False

    def seal_bytes(self, raw, label):
        if self.key is None:
            raise ValueError("Configure GIVELIFE_STORAGE_KEY before creating encrypted backups.")
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        nonce = os.urandom(12)
        return nonce + AESGCM(self.key).encrypt(nonce, raw, label.encode())

    def open_bytes(self, raw, label):
        if self.key is None:
            raise ValueError("Encrypted state requires the original GIVELIFE_STORAGE_KEY.")
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        try:
            return AESGCM(self.key).decrypt(raw[:12], raw[12:], label.encode())
        except Exception:
            raise ValueError(
                "Encrypted data could not be authenticated. Check the storage key; data was not changed."
            ) from None

    def encode(self, raw, key):
        if not self.key:
            return raw
        return json.dumps(
            {
                "format": MARKER,
                "data": base64.b64encode(self.seal_bytes(raw.encode(), "record:" + key)).decode(),
            }
        )

    def decode(self, raw, key):
        if not self.encrypted(raw):
            return raw
        try:
            blob = base64.b64decode(json.loads(raw)["data"], validate=True)
        except Exception:
            raise ValueError("Encrypted state envelope is invalid; data was not changed.") from None
        return self.open_bytes(blob, "record:" + key).decode()
