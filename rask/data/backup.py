"""
backup.py — Encrypted backup/restore for Rask data.

Format (binary, all big-endian):
    [magic:4]   b"RASK"
    [ver:1]     1
    [salt:16]
    [iv:16]
    [ciphertext_len:4]
    [ciphertext:N]

Key derivation: PBKDF2-HMAC-SHA256, 200k iterations.
Cipher: AES-256-CBC with PKCS7 padding.

Plaintext payload is a JSON document containing all rows of every table.
"""
from __future__ import annotations

import json
import os
import struct
from datetime import datetime
from pathlib import Path
from typing import Optional

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding as sym_padding

from rask import config as cfg
from rask.data import database as db


def _derive_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=cfg.BACKUP_KEY_LEN,
        salt=salt,
        iterations=cfg.BACKUP_KDF_ITERATIONS,
    )
    return kdf.derive(password.encode("utf-8"))


def _encrypt(plaintext: bytes, password: str) -> bytes:
    salt = os.urandom(cfg.BACKUP_SALT_LEN)
    iv = os.urandom(cfg.BACKUP_IV_LEN)
    key = _derive_key(password, salt)
    padder = sym_padding.PKCS7(algorithms.AES.block_size).padder()
    padded = padder.update(plaintext) + padder.finalize()
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    enc = cipher.encryptor()
    ct = enc.update(padded) + enc.finalize()
    return (
        cfg.BACKUP_MAGIC
        + struct.pack(">B", cfg.BACKUP_VERSION)
        + salt
        + iv
        + struct.pack(">I", len(ct))
        + ct
    )


def _decrypt(blob: bytes, password: str) -> bytes:
    if blob[:4] != cfg.BACKUP_MAGIC:
        raise ValueError("Not a Rask backup file (bad magic).")
    ver = struct.unpack(">B", blob[4:5])[0]
    if ver != cfg.BACKUP_VERSION:
        raise ValueError(f"Unsupported backup version {ver}.")
    salt = blob[5:5 + cfg.BACKUP_SALT_LEN]
    iv = blob[5 + cfg.BACKUP_SALT_LEN:5 + cfg.BACKUP_SALT_LEN + cfg.BACKUP_IV_LEN]
    ct_len = struct.unpack(">I",
        blob[5 + cfg.BACKUP_SALT_LEN + cfg.BACKUP_IV_LEN:
             9 + cfg.BACKUP_SALT_LEN + cfg.BACKUP_IV_LEN])[0]
    ct_start = 9 + cfg.BACKUP_SALT_LEN + cfg.BACKUP_IV_LEN
    ct = blob[ct_start:ct_start + ct_len]
    key = _derive_key(password, salt)
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    dec = cipher.decryptor()
    padded = dec.update(ct) + dec.finalize()
    unpadder = sym_padding.PKCS7(algorithms.AES.block_size).unpadder()
    return unpadder.update(padded) + unpadder.finalize()


# === Export / import ===

def export_to_file(path: Path, password: str) -> None:
    payload = _collect_payload()
    blob = _encrypt(json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                    password)
    path.write_bytes(blob)


def export_to_bytes(password: str) -> bytes:
    payload = _collect_payload()
    return _encrypt(json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                    password)


def import_from_file(path: Path, password: str, replace: bool = True) -> None:
    blob = path.read_bytes()
    data = _decrypt(blob, password)
    payload = json.loads(data.decode("utf-8"))
    _apply_payload(payload, replace=replace)


def import_from_bytes(blob: bytes, password: str, replace: bool = True) -> None:
    data = _decrypt(blob, password)
    payload = json.loads(data.decode("utf-8"))
    _apply_payload(payload, replace=replace)


# === Payload ===

TABLES = [
    "categories", "activities", "goals", "streaks",
    "templates", "badges", "kv_store",
]


def _collect_payload() -> dict:
    payload = {
        "version": cfg.BACKUP_VERSION,
        "app_version": cfg.APP_VERSION,
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "tables": {},
    }
    for t in TABLES:
        rows = db.query_all(f"SELECT * FROM {t}")
        payload["tables"][t] = [dict(r) for r in rows]
    return payload


def _apply_payload(payload: dict, replace: bool = True) -> None:
    conn = db.get_connection()
    with db._LOCK:
        if replace:
            for t in TABLES:
                conn.execute(f"DELETE FROM {t}")
        for t in TABLES:
            for row in payload.get("tables", {}).get(t, []):
                cols = list(row.keys())
                placeholders = ",".join(["?"] * len(cols))
                colnames = ",".join(cols)
                conn.execute(
                    f"INSERT INTO {t}({colnames}) VALUES ({placeholders})",
                    [row[c] for c in cols],
                )
