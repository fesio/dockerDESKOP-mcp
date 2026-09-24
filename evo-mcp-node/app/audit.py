from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class AuditLogger:
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    def write(self, action: str, outcome: str, **details: Any) -> None:
        payload = {
            "ts": datetime.now(UTC).isoformat(),
            "action": action,
            "outcome": outcome,
            **details,
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self._lock, self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
        except OSError:
            return
