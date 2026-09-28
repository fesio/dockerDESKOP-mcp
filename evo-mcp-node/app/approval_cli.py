from __future__ import annotations

import argparse
import sys

from app.approvals import create_approval_token


def build_token(secret: str, action: str, target: str, ttl_seconds: int) -> str:
    if len(secret) < 32:
        raise ValueError("approval secret must contain at least 32 characters")
    return create_approval_token(secret, action, target, ttl_seconds)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create one scoped Evo MCP approval token")
    parser.add_argument("--action", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--ttl", type=int, default=300)
    args = parser.parse_args()
    secret = sys.stdin.readline().rstrip("\r\n")
    print(build_token(secret, args.action, args.target, args.ttl))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
