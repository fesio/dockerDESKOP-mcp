# Evo MCP Node

Prywatny serwer Model Context Protocol do uruchamiania lokalnie w Docker Desktop oraz późniejszego hostowania z tego samego Dockerfile.

## Jedna komenda lokalnie

W PowerShell, w katalogu `evo-mcp-node`:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\setup.ps1
```

Skrypt automatycznie sprawdza Docker Desktop, tworzy lokalny `.env` i losowy token, buduje etap testowy, uruchamia testy, buduje runtime, uruchamia Compose i czeka na healthcheck.

Po uruchomieniu:

- MCP: `http://127.0.0.1:8765/mcp`
- Health: `http://127.0.0.1:8765/health`
- Ready: `http://127.0.0.1:8765/ready`

Port jest publikowany wyłącznie na `127.0.0.1`. Kontener ma `restart: unless-stopped`, działa jako użytkownik non-root, ma read-only filesystem, `cap_drop: ALL`, `no-new-privileges`, limity CPU/RAM/PID oraz rotację logów.

## Zarządzanie

```powershell
.\scripts\start.ps1
.\scripts\status.ps1
.\scripts\logs.ps1
.\scripts\stop.ps1
```

## Hosting

Ten sam obraz można wdrożyć do Google Cloud Run:

```powershell
.\scripts\deploy-cloudrun.ps1 -ProjectId TWOJ_PROJECT_ID
```

Skrypt włącza wymagane API, zapisuje prywatny token w Google Secret Manager i wdraża bieżący Dockerfile. W hostowanej wersji `/mcp` wymaga Bearer Token; `/health` pozostaje publicznym, niewrażliwym healthcheckiem.

## Struktura

- `app/` — serwer MCP, logowanie, konfiguracja i middleware.
- `tests/` — testy narzędzi MCP, konfiguracji i health/readiness.
- `scripts/` — automatyzacja Windows/Docker/Cloud Run.
- `Dockerfile` — osobny target test i utwardzony runtime.
- `compose.yaml` — lokalny Docker Desktop.
- `.env.example` — szablon bez sekretów.

Sekretów nie zapisuj w Git. Lokalny `.env` jest ignorowany.
