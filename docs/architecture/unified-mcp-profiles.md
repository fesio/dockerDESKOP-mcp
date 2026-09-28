# ADR-001: Jeden Evo MCP z rozdzielonymi profilami narzędzi

**Status:** Accepted
**Date:** 2026-09-28

## Context

Projekt miał trzy rozproszone uruchomienia: historyczny Docker Hub MCP, Evo MCP oraz osobny proxy. Narzędzia programistyczne i n8n były publikowane w jednej liście, przez co aplikacje klienckie widziały funkcje, których nie potrzebowały.

## Decision

`evo-mcp-node` jest kanonicznym obrazem serwera. Ten sam obraz uruchamia się w jednym projekcie Docker Compose jako dwa profile:

- `evo-mcp-apps` na `127.0.0.1:8765/mcp` — brain, workspace, Git, testy, lint, Docker i długie zadania;
- `evo-mcp-n8n` na `127.0.0.1:8766/mcp` — tylko narzędzia n8n oraz wspólne status/echo.

Oba profile korzystają z jednego kodu, obrazu, zasad autoryzacji, audytu i pipeline'u CI. Dane wykonawcze są rozdzielone na osobne wolumeny, aby uniknąć współdzielenia SQLite pomiędzy procesami. Główny `compose.yaml` w repozytorium dołącza kanoniczną definicję z `evo-mcp-node/compose.yaml`.

## Options considered

1. Jeden endpoint ze wszystkimi narzędziami — najprostszy, ale miesza uprawnienia i kontekst aplikacji.
2. Dwa osobne projekty i obrazy — dobre rozdzielenie, lecz dubluje kod i wdrożenia.
3. Jeden obraz z dwoma profilami — wybrany wariant; daje separację narzędzi bez rozjazdu implementacji.

## Consequences

- Klient n8n nie otrzymuje narzędzi plikowych, Git ani Docker.
- Klienci programistyczni nie otrzymują narzędzi modyfikujących workflow n8n.
- Aktualizacja jednego obrazu aktualizuje oba profile.
- Hosting chmurowy może uruchomić profil `all`, `apps` albo `n8n` przez `MCP_TOOL_PROFILE`.
