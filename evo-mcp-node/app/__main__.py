from __future__ import annotations

import uvicorn

from app.config import Settings


def main() -> None:
    settings = Settings.from_env()
    uvicorn.run(
        "app.server:app",
        host=settings.bind_host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        access_log=False,
        proxy_headers=settings.trust_proxy,
        forwarded_allow_ips="*" if settings.trust_proxy else "127.0.0.1",
        timeout_graceful_shutdown=15,
        timeout_keep_alive=10,
    )


if __name__ == "__main__":
    main()
