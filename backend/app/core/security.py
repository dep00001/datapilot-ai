from __future__ import annotations
import hashlib
import hmac
import secrets
from datetime import datetime, timezone
from pathlib import Path
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from fastapi import HTTPException
from app.core.config import settings, STORAGE_DIR

# Argon2id password hasher with 19MB memory cost, 2 iterations, 1 parallelism lane
ph = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)

def hash_password(password: str) -> str:
    return ph.hash(password)

def verify_password(password_hash: str, password: str) -> bool:
    try:
        return ph.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError):
        return False

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode('utf-8')).hexdigest()

def otp_digest(code: str) -> str:
    return hmac.new(settings.app_secret_key.encode('utf-8'), code.encode('utf-8'), hashlib.sha256).hexdigest()

def verify_otp_digest(code: str, expected_digest: str) -> bool:
    actual = otp_digest(code)
    return hmac.compare_digest(actual, expected_digest)

def generate_otp() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"

def generate_session_token() -> str:
    return secrets.token_urlsafe(48)

def normalize_email(email: str) -> str:
    return email.strip().lower()

def safe_filename(filename: str) -> str:
    cleaned = Path(filename or 'dataset.csv').name
    for bad in ['\\', '/', '..', ':', '*', '?', '"', '<', '>', '|']:
        cleaned = cleaned.replace(bad, '_')
    return cleaned[:180] or 'dataset.csv'

def user_storage_dir(user_id: str) -> Path:
    target = (STORAGE_DIR / user_id).resolve()
    if STORAGE_DIR not in target.parents and target != STORAGE_DIR:
        raise HTTPException(status_code=400, detail="Invalid storage path detected.")
    target.mkdir(parents=True, exist_ok=True)
    return target
