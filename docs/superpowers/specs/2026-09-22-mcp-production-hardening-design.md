# MCP Production Hardening — Design

Date: 2026-09-22
Repository: fesio/dockerDESKOP-mcp
Branch: feat/mcp-production-hardening

## Goal
Turn the currently verified local Docker MCP into a durable, secure, reproducible deployment that survives Docker Desktop restarts and can later be exposed at https://mcp.fesiomatyzacja.pro/mcp without duplicating repositories or leaking secrets.

## Current verified state
- Docker Desktop on Yoggi is online and usable.
- Image fesio-mcp:latest builds from commit 0ced2c2.
- Container fesio-mcp runs on port 3000 with restart=unless-stopped.
- POST /mcp returns HTTP 200 and MCP protocolVersion 2025-06-18.
- A temporary Cloudflare Quick Tunnel also returns a successful public MCP handshake.
- DNS for fesiomatyzacja.pro is currently hosted by OVH, not Cloudflare.
- src/server.ts logs the entire incoming MCP request body.
- The public MCP endpoint currently has no server-side client authentication or rate limiting.
- Docker Scout reports critical/high findings in the current image and recommends moving away from node:current-alpine3.22.

## Success criteria
1. One canonical repository remains the source of truth.
2. Docker Desktop can recreate the full runtime from Compose after a restart.
3. No raw secrets are committed to Git or printed in application logs.
4. Health and readiness endpoints provide machine-verifiable status.
5. MCP requests are authenticated before reaching privileged tool execution.
6. Request body size and request rate are bounded.
7. Runtime uses a pinned Node LTS base image and remains non-root.
8. Build, tests, security checks, restart test, local handshake, and public handshake are all verified before release.

## Runtime architecture
Docker Compose will define the durable local stack:
- fesio-mcp: application container built from the canonical repository.
- cloudflared: named-tunnel client once Cloudflare DNS/tunnel authorization exists.
- fesio-mcp-net: private Docker bridge network.
- Named volumes only where durable application state is actually required.

The MCP container will expose port 3000 to localhost for local clients. Public traffic will reach MCP only through the tunnel/reverse-proxy path. Direct internet exposure of port 3000 is not part of the design.

## Docker persistence model
The repository is the authoritative copy of source and deployment configuration. Docker Desktop stores the built image, containers, networks, and runtime metadata, but is not treated as the source-code backup. Compose must be sufficient to recreate the stack from the repository.

The Compose project will use:
- restart: unless-stopped
- healthcheck for the application
- dependency ordering based on health
- explicit image/build definitions
- a stable project/network name
- security_opt: no-new-privileges:true
- cap_drop: ALL where compatible
- read_only where compatible with the runtime
- tmpfs for required ephemeral writable paths

## HTTP/MCP surface
POST /mcp remains the MCP endpoint.
GET /mcp and DELETE /mcp remain non-operational protocol routes.
GET /health reports process liveness only.
GET /readiness reports whether the MCP server is ready to accept protocol requests.
JSON request size is bounded.
Logs contain request identifiers, method/status metadata, and duration, never full request bodies or authorization values.

## Authentication and abuse controls
The public MCP route will require a bearer token from an environment variable or managed secret. Missing or invalid credentials fail closed before MCP dispatch. Health/readiness endpoints remain non-sensitive and do not disclose secrets or internal configuration.

A bounded in-memory rate limiter is sufficient for the first local single-instance deployment. If the service becomes multi-instance, the limiter moves to a shared backend or edge layer. Request-size limits and timeout behavior must be explicit.

## Supply-chain and image policy
Dockerfile will use a pinned Node 24 Alpine image rather than node:current. The container keeps a non-root runtime user. Dependency updates are targeted; no automatic npm audit fix --force is allowed.

Docker Scout and npm audit are evidence sources, not automatic proof of exploitability. Security review traces findings to reachable runtime paths before labeling them blocking.

## NORA / Brain relationship
brain/server.ts remains a separate control-plane entrypoint. NORA/Brain chooses tools, memory, routing, and approvals. n8n remains an optional execution adapter and does not become the primary planner.

Noodle Seed validation is used where compatible with the existing Brain entrypoint. It must not overwrite unrelated repository structure.

## Domain and tunnel
Target public URL: https://mcp.fesiomatyzacja.pro/mcp.
Current DNS authority is OVH. A stable Cloudflare Named Tunnel requires explicit Cloudflare account authorization and a DNS path under Cloudflare control. Until that authorization is available, the existing Quick Tunnel is treated as temporary only.

No DNS nameserver migration is performed implicitly. If Cloudflare DNS migration is chosen, it is a separate user-visible infrastructure change. If OVH DNS is retained, the design must use a compatible CNAME/reverse-proxy strategy instead.

## Verification gates
Before release:
- npm test / project test suite passes.
- npm run build passes.
- lint/format checks pass where configured.
- Docker image builds from a clean checkout.
- Docker Scout results are reviewed after the base-image change.
- Compose restart recreates a healthy stack.
- Local MCP initialize returns HTTP 200.
- Public HTTPS MCP initialize returns HTTP 200 when a stable tunnel is configured.
- Logs are checked for secret/request-body leakage.
- git status is clean after the final commit.

## Non-goals
This change does not redesign every Docker Hub MCP tool, migrate all NORA logic into src/, add a new database, or replace GitHub with Docker Desktop.
