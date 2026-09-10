"""Per-license Ed25519 signing keys for the registry.

Private keys live on disk under KEYS_DIR (gitignored) — one file per license id.
They are never returned through the API. Public keys are stored on the User row.
"""
from __future__ import annotations

from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from app.core.config import settings

_KEYS = Path(settings.KEYS_DIR)


def _priv_path(license_id: str) -> Path:
    return _KEYS / f"{license_id}.key"


def ensure_keypair(license_id: str) -> str:
    """Create the keypair for a license if missing. Returns public key hex."""
    _KEYS.mkdir(parents=True, exist_ok=True)
    p = _priv_path(license_id)
    if not p.exists():
        priv = Ed25519PrivateKey.generate()
        p.write_bytes(
            priv.private_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PrivateFormat.Raw,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
    return public_key_hex(license_id)


def _load_priv(license_id: str) -> Ed25519PrivateKey:
    raw = _priv_path(license_id).read_bytes()
    return Ed25519PrivateKey.from_private_bytes(raw)


def public_key_hex(license_id: str) -> str:
    priv = _load_priv(license_id)
    pub = priv.public_key()
    return pub.public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    ).hex()


def sign(license_id: str, message: str) -> str:
    priv = _load_priv(license_id)
    return priv.sign(message.encode()).hex()


def verify(public_key_hex_str: str, message: str, signature_hex: str) -> bool:
    try:
        pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex_str))
        pub.verify(bytes.fromhex(signature_hex), message.encode())
        return True
    except Exception:
        return False
