from __future__ import annotations

import threading
from collections import defaultdict
from typing import Any

SECRET_KEYS = {
    "authorization",
    "api_key",
    "apikey",
    "token",
    "secret",
    "password",
    "credentials",
    "cookie",
    "set-cookie",
}


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if str(key).lower() in SECRET_KEYS else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    return value


class Metrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._requests: dict[tuple[str, str], int] = defaultdict(int)
        self._duration_seconds = 0.0

    def observe(self, method: str, status: int, duration_seconds: float) -> None:
        status_class = f"{max(0, status) // 100}xx"
        with self._lock:
            self._requests[(method.upper(), status_class)] += 1
            self._duration_seconds += max(0.0, duration_seconds)

    def render(self) -> str:
        with self._lock:
            rows = [
                "# HELP evo_http_requests_total HTTP requests by method and status class.",
                "# TYPE evo_http_requests_total counter",
            ]
            for (method, status_class), count in sorted(self._requests.items()):
                rows.append(
                    f'evo_http_requests_total{{method="{method}",status_class="{status_class}"}} {count}'
                )
            rows.extend(
                [
                    "# HELP evo_http_request_duration_seconds_sum Total request duration.",
                    "# TYPE evo_http_request_duration_seconds_sum counter",
                    f"evo_http_request_duration_seconds_sum {self._duration_seconds:.6f}",
                ]
            )
        return "\n".join(rows) + "\n"


metrics = Metrics()
