from __future__ import annotations
import time
from fastapi import HTTPException, Request
from app.core.config import settings

_HIT_STORE: dict[str, list[float]] = {}

def check_rate_limit(request: Request, action: str, max_requests: int | None = None, window_seconds: int = 60):
    client_ip = request.client.host if request.client else "unknown"
    key = f"{client_ip}:{action}"
    now = time.time()
    cutoff = now - window_seconds
    limit = max_requests or settings.auth_rate_limit_per_minute

    hits = [t for t in _HIT_STORE.get(key, []) if t > cutoff]
    if len(hits) >= limit:
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please slow down and try again shortly."
        )
    hits.append(now)
    _HIT_STORE[key] = hits

def clear_rate_limits():
    """Testing helper to reset rate limit hits."""
    _HIT_STORE.clear()
