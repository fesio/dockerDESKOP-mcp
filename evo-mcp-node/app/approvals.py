from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path


class ApprovalError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ApprovalClaims:
    action: str
    target: str
    expires_at: int
    nonce: str


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def create_approval_token(secret: str, action: str, target: str, ttl_seconds: int = 300) -> str:
    if len(secret) < 32:
        raise ApprovalError("approval secret must contain at least 32 characters")
    claims = {
        "action": action,
        "target": target,
        "expires_at": int(time.time()) + ttl_seconds,
        "nonce": secrets.token_urlsafe(18),
    }
    payload = json.dumps(claims, sort_keys=True, separators=(",", ":")).encode()
    signature = hmac.new(secret.encode(), payload, hashlib.sha256).digest()
    return f"{_encode(payload)}.{_encode(signature)}"


class ApprovalVerifier:
    def __init__(self, secret: str, database_path: str | Path) -> None:
        self.secret = secret
        self.database_path = Path(database_path)

    def _connect(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path)
        connection.execute(
            "CREATE TABLE IF NOT EXISTS used_approvals (nonce TEXT PRIMARY KEY, used_at INTEGER NOT NULL)"
        )
        return connection

    def verify(self, token: str, action: str, target: str) -> ApprovalClaims:
        if len(self.secret) < 32:
            raise ApprovalError("destructive actions require PROGRAMMER_APPROVAL_SECRET")
        try:
            payload_text, signature_text = token.split(".", 1)
            payload = _decode(payload_text)
            supplied_signature = _decode(signature_text)
            raw = json.loads(payload)
            claims = ApprovalClaims(
                action=str(raw["action"]),
                target=str(raw["target"]),
                expires_at=int(raw["expires_at"]),
                nonce=str(raw["nonce"]),
            )
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ApprovalError("invalid approval token") from exc
        expected_signature = hmac.new(self.secret.encode(), payload, hashlib.sha256).digest()
        if not hmac.compare_digest(supplied_signature, expected_signature):
            raise ApprovalError("invalid approval token signature")
        if claims.action != action or claims.target != target:
            raise ApprovalError("approval token scope does not match this action and target")
        if claims.expires_at < int(time.time()):
            raise ApprovalError("approval token has expired")
        with self._connect() as connection:
            try:
                connection.execute(
                    "INSERT INTO used_approvals(nonce, used_at) VALUES (?, ?)",
                    (claims.nonce, int(time.time())),
                )
            except sqlite3.IntegrityError as exc:
                raise ApprovalError("approval token was already used") from exc
        return claims
