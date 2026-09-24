# Evo MCP Node 0.2

Local-first MCP dla programisty, Docker Desktop i n8n. Ten sam obraz może później działać za reverse proxy / Cloud Run.

## Najszybszy start

### Tylko Evo MCP

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\setup.ps1
```

### Evo MCP + lokalny n8n 2.40.5

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\setup.ps1 -WithN8n
```

Po starcie:

- Evo MCP: `http://127.0.0.1:8765/mcp`
- Health: `http://127.0.0.1:8765/health`
- n8n UI: `http://127.0.0.1:5678`

## Jednorazowe połączenie n8n

n8n wymaga utworzenia właściciela i jawnego włączenia instance-level MCP. Nie omijamy tego mechanizmu bezpieczeństwa.

1. Otwórz `http://127.0.0.1:5678` i dokończ pierwszy setup n8n.
2. W ustawieniach n8n włącz **MCP access** i utwórz token API dla MCP.
3. Opcjonalnie utwórz zwykły n8n REST API key (REST jest fallbackiem administracyjnym).
4. Uruchom:

```powershell
.\scripts\configure-n8n.ps1
```

Skrypt poprosi o sekrety w maskowanych polach, zapisze je wyłącznie w `.env` i zrestartuje Evo MCP.

## Co potrafi profil programisty

Profile:

- `read` — drzewo repo, odczyt/szukaj, `git status`, `git diff`.
- `standard` — dodatkowo zapis plików, allow-list command runner, branche, commit, testy/lint przez narzędzia projektu, tworzenie/edycja/testowanie/publikowanie workflow n8n.
- `autonomous` — dodatkowo operacje wymagające lokalnego `PROGRAMMER_APPROVAL_SECRET`, np. usuwanie plików i `git push`.

Workspace jest zawsze jailowany do `/workspace`; ścieżki absolutne i `../` poza workspace są blokowane. Polecenia są uruchamiane bez shella, z timeoutem i allow-listą.

### Docker Desktop jako narzędzie programisty

Dostęp do socketu Docker jest celowo wyłączony domyślnie, ponieważ daje bardzo szeroką kontrolę nad hostem. Na zaufanym komputerze można go jawnie włączyć:

```powershell
.\scripts\enable-docker-tools.ps1
```

Skrypt wykrywa GID socketa i uruchamia utwardzony wariant `host-tools`.

## n8n: natywne MCP + REST fallback

Preferowana ścieżka to n8n instance-level MCP pod:

```text
http://n8n:5678/mcp-server/http
```

Evo MCP ma narzędzia/wrappers dla m.in.:

- `search_workflows`, `get_workflow_details`;
- `get_workflow_sdk_reference`, `get_workflow_best_practices`;
- `search_nodes`, `get_node_types`, `explore_node_resources`;
- `validate_node_config`, `validate_workflow`;
- `create_workflow_from_code`;
- atomowego `update_workflow`;
- `prepare_workflow_pin_data`, `test_workflow`;
- `execute_workflow` + `get_workflow_execution`;
- `search_workflow_executions`;
- historii/wersji: `get_workflow_history`, `get_workflow_version`, `get_workflow_versions_diff`, `restore_workflow_version`;
- `publish_workflow`, `unpublish_workflow`;
- projektów/folderów/tagów/credentials.

`archive_*`/`delete_*` są blokowane w generycznym bridge nawet jeśli ktoś omyłkowo dopisze je do allow-listy.

### Budowanie workflow z naturalnego opisu

MCP wystawia prompt `n8n_workflow_builder`. Model dostaje wymuszoną sekwencję:

1. pobierz aktualną referencję Workflow SDK;
2. pobierz best practices i wyszukaj aktualne node types;
3. zwaliduj node config;
4. wygeneruj kod Workflow SDK;
5. `validate_workflow`;
6. `create_workflow_from_code` albo atomowy `update_workflow`;
7. `prepare_workflow_pin_data` + `test_workflow`;
8. sprawdź execution/history/diff;
9. dopiero wtedy `publish_workflow`.

Dzięki temu model nie musi znać na pamięć aktualnych parametrów node'ów i nie powinien wymyślać nieistniejących typów.

## Observability

Każde żądanie ma `X-Request-ID`, logi są JSON, a operacje zapisu/komend/n8n są audytowane do `/data/audit.jsonl`.

OpenTelemetry jest opcjonalne. Wystarczy ustawić standardowe zmienne, np.:

```text
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
OTEL_SERVICE_NAME=evo-mcp-node
```

Bez endpointu OTel nie dodaje narzutu eksportera.

## Bezpieczeństwo

- lokalny port MCP: tylko `127.0.0.1`;
- non-root, read-only root filesystem, `cap_drop: ALL`, `no-new-privileges`;
- sekrety tylko w `.env`/Secret Manager, nigdy w Git;
- n8n host allow-list zapobiega użyciu integracji jako dowolnego proxy SSRF;
- natywne n8n MCP ma osobną allow-listę tools;
- operacje destrukcyjne n8n są blokowane w bridge;
- `git push`/delete plików wymagają profilu `autonomous` + sekretu approval;
- Docker socket wymaga osobnego jawnego opt-in.

## Zarządzanie

```powershell
.\scripts\start.ps1
.\scripts\start-with-n8n.ps1
.\scripts\status.ps1
.\scripts\logs.ps1
.\scripts\verify-n8n.ps1
.\scripts\stop.ps1
```

## Hosting Cloud Run

Po jednorazowym `gcloud auth login`:

```powershell
.\scripts\deploy-cloudrun.ps1 -ProjectId TWOJ_PROJECT_ID
```

Skrypt tworzy/uaktualnia Secret Manager i wdraża ten sam Dockerfile. Hostowany `/mcp` wymaga Bearer tokenu. Profil programisty w Cloud Run jest ustawiany na `read`; lokalny Docker pozostaje miejscem do edycji repo i dostępu do narzędzi hosta.


## Bezkluczowe CI/CD do Cloud Run (GitHub OIDC / WIF)

Projekt zawiera workflow `evo-mcp-cloudrun.yml`, który uwierzytelnia GitHub Actions do Google Cloud przez OIDC + Workload Identity Federation — bez długowiecznego klucza JSON.

Jednorazowa konfiguracja z komputera, na którym działa `gcloud`:

```powershell
.\scripts\setup-gcp-wif.ps1 -ProjectId TWOJ_PROJECT_ID
```

Skrypt:
- włącza potrzebne API Google Cloud;
- tworzy/wykorzystuje konto `evo-mcp-github`;
- konfiguruje Workload Identity Pool + GitHub OIDC ograniczony do repo `fesio/dockerDESKOP-mcp`;
- nadaje role wymagane do source deploymentu Cloud Run i konfiguracji sekretów;
- nadaje Cloud Build wymagane `roles/run.builder`;
- zapisuje lokalny MCP token w Secret Manager;
- jeśli `gh` jest zalogowane, sam ustawia `GCP_PROJECT_ID`, `GCP_WIF_PROVIDER` i `GCP_SERVICE_ACCOUNT` jako GitHub Repository Variables.

Potem hosting uruchamiasz z GitHub Actions -> **evo-mcp-cloudrun** -> **Run workflow**. Workflow po deploymencie wykonuje `/health` i zapisuje prawdziwy adres `https://...run.app/mcp` w podsumowaniu joba.

W chmurze profil programisty pozostaje `read`; edycja repo, Docker socket i operacje autonomiczne są przeznaczone dla lokalnej instancji Docker Desktop.
