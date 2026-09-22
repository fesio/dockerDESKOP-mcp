# MCP Production Hardening — Implementation Plan

Date: 2026-09-22
Spec: docs/superpowers/specs/2026-09-22-mcp-production-hardening-design.md
Repository: fesio/dockerDESKOP-mcp
Branch: feat/mcp-production-hardening

## Goal
Ship a durable Docker Desktop deployment of the canonical MCP server with fail-closed HTTP authentication, bounded request handling, container-native logging, health/readiness probes, a pinned Node 24 runtime, reproducible Compose, CI verification, NORA/Brain validation, and a production-grade stable tunnel path.

## File map
- Create: src/runtimeConfig.ts — runtime/secret/config resolution.
- Create: src/httpSecurity.ts — bearer auth and fixed-window rate limiting.
- Modify: src/index.ts — use resolved config; stop logging raw argv.
- Modify: src/server.ts — protected MCP route, health/readiness, JSON limit, safe request metadata.
- Modify: src/logger.ts — stdout/stderr by default; file logging only when explicitly requested.
- Create: test/runtime-config.test.mjs — config and secret-file behavior.
- Create: test/http-security.test.mjs — auth/rate-limit primitives.
- Create: test/server-http.test.mjs — end-to-end HTTP MCP behavior.
- Modify: package.json / package-lock.json — test and verify scripts only; targeted dependency updates if justified.
- Modify: Dockerfile — pinned Node 24 Alpine, deterministic install, non-root hardened runtime.
- Create: compose.yaml — persistent Docker Desktop stack.
- Create: .env.example — non-secret runtime defaults.
- Modify: .gitignore — ignore local secret material.
- Create: .github/workflows/verify.yml — build/test/lint/format/Docker build.
- Optional after validation only: docs/security/mcp-threat-model.md — evidence-backed security findings.

## Global constraints
- Keep one canonical repository: fesio/dockerDESKOP-mcp.
- Preserve stdio transport behavior.
- HTTP transport fails closed when no MCP bearer secret is available.
- Never commit or print raw MCP, Docker Hub, Cloudflare, Telegram, OpenAI, Gemini, or other credentials.
- Bind host port 3000 to 127.0.0.1 only.
- Use Docker secrets/file mounts for MCP and Cloudflare tunnel tokens.
- Do not use npm audit fix --force.
- NORA/Brain remains the control plane; n8n remains an optional executor.
- Do not merge or claim production readiness until every verification gate is freshly rerun.

## Review focus
1. HTTP mode started without a token must fail explicitly instead of starting insecurely.
2. Missing, malformed, or near-match bearer tokens must return 401 and never reach MCP dispatch.
3. Oversized JSON must return 413 before tool execution and must not be echoed to logs.
4. Rate limiting must reset after its window and must not block /health or /readiness.
5. Docker restart must recreate a healthy MCP when secret files exist; missing secret files must fail closed.

---

### Task 1: Add the test harness and runtime configuration contract

**Files:**
- Create: src/runtimeConfig.ts
- Create: test/runtime-config.test.mjs
- Modify: package.json

**Interfaces:**
- Produces: `RuntimeConfig`
- Produces: `resolveRuntimeConfig(args: string[], env: NodeJS.ProcessEnv): RuntimeConfig`
- Produces: `readSecretFile(path: string): string`

- [ ] **Step 1: Write failing runtime config tests**

Create `test/runtime-config.test.mjs` using Node's built-in `node:test`.

```js
import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';

test('http mode rejects missing MCP auth token', async () => {
  const { resolveRuntimeConfig } = await import('../dist/runtimeConfig.js');
  assert.throws(
    () => resolveRuntimeConfig(['--transport=http'], {}),
    /MCP authentication token is required/
  );
});

test('secret file is preferred over environment token', async () => {
  const dir = mkdtempSync(join(tmpdir(), 'mcp-secret-'));
  const file = join(dir, 'token');
  writeFileSync(file, 'file-token\n');
  const { resolveRuntimeConfig } = await import('../dist/runtimeConfig.js');
  const cfg = resolveRuntimeConfig(
    ['--transport=http'],
    { MCP_AUTH_TOKEN: 'env-token', MCP_AUTH_TOKEN_FILE: file }
  );
  assert.equal(cfg.mcpAuthToken, 'file-token');
});
```

- [ ] **Step 2: Add test scripts and verify RED**

Modify `package.json`:
```json
"test": "npm run build && node --test test/*.test.mjs",
"verify": "npm run test && npm run lint && npm run format:check"
```

Run:
```powershell
npm.cmd test
```
Expected: FAIL because `dist/runtimeConfig.js` does not exist.

- [ ] **Step 3: Implement minimal runtimeConfig.ts**

Required behavior:
- CLI `--transport` and `--port` remain supported.
- `MCP_TRANSPORT` / `PORT` are fallback inputs.
- `MCP_AUTH_TOKEN_FILE` takes precedence over `MCP_AUTH_TOKEN`.
- HTTP transport requires a non-empty auth token.
- stdio does not require MCP HTTP auth.
- Defaults: port 3000, rate 60/minute, JSON limit `1mb`.
- Reject invalid port/rate values instead of silently weakening behavior.

- [ ] **Step 4: Run tests and full build**

Run:
```powershell
npm.cmd test
npm.cmd run build
```
Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add package.json package-lock.json src/runtimeConfig.ts test/runtime-config.test.mjs
git commit -m "test: define secure MCP runtime configuration"
```

---

### Task 2: Add authentication and rate-limit primitives test-first

**Files:**
- Create: src/httpSecurity.ts
- Create: test/http-security.test.mjs

**Interfaces:**
- `isBearerAuthorized(header: string | undefined, expectedToken: string): boolean`
- `createFixedWindowLimiter(limit: number, windowMs: number, now?: () => number)`
- limiter exposes `allow(key: string): boolean`

- [ ] **Step 1: Write failing security tests**

Cover:
- exact bearer token accepted;
- missing token rejected;
- malformed scheme rejected;
- prefix/suffix/near-match token rejected;
- limiter blocks request N+1;
- limiter resets after the window.

Example:
```js
test('near-match bearer token is rejected', async () => {
  const { isBearerAuthorized } = await import('../dist/httpSecurity.js');
  assert.equal(isBearerAuthorized('Bearer secret-x', 'secret'), false);
});
```

- [ ] **Step 2: Run targeted tests and verify RED**
```powershell
npm.cmd run build
node --test test/http-security.test.mjs
```

- [ ] **Step 3: Implement minimal security primitives**

Use `crypto.timingSafeEqual` only after equal-length buffers are established. Never include supplied/expected token values in thrown errors or logs.

- [ ] **Step 4: Verify GREEN**
```powershell
npm.cmd test
```

- [ ] **Step 5: Commit**
```bash
git add src/httpSecurity.ts test/http-security.test.mjs
git commit -m "feat: add MCP HTTP security primitives"
```

---

### Task 3: Harden the HTTP MCP surface and logging

**Files:**
- Modify: src/server.ts
- Modify: src/index.ts
- Modify: src/logger.ts
- Create: test/server-http.test.mjs

**Behavior contract:**
- `GET /health` -> 200 `{"status":"ok"}`.
- `GET /readiness` -> 200 only after HTTP listener is ready.
- `POST /mcp` without valid bearer token -> 401.
- Auth occurs before JSON parsing and MCP dispatch.
- JSON parser uses configured size limit.
- Valid authenticated initialize -> MCP HTTP 200.
- Rate-limit overflow -> 429.
- Logs never contain request bodies or Authorization values.
- `GET /mcp` / `DELETE /mcp` remain protocol-disabled.
- Production logs go to Docker stdout/stderr unless `--logs-dir` is explicitly supplied.

- [ ] **Step 1: Write end-to-end failing tests**

The test spawns:
```js
spawn(process.execPath, ['dist/index.js', '--transport=http', `--port=${port}`], {
  env: {
    ...process.env,
    NODE_ENV: 'production',
    MCP_AUTH_TOKEN: 'test-token',
    MCP_RATE_LIMIT_PER_MINUTE: '2'
  }
});
```

Assertions:
- poll `/health` until 200;
- `/readiness` is 200 after startup;
- no-auth POST is 401;
- valid initialization with `Authorization: Bearer test-token` is 200;
- oversized payload is 413;
- third request inside rate window is 429;
- captured logs do not contain a sentinel value embedded in a request body;
- startup metadata is visible in captured stdout/stderr.

- [ ] **Step 2: Verify RED**
```powershell
npm.cmd test
```

- [ ] **Step 3: Implement the minimal route/middleware changes**

Order for `/mcp`:
1. bearer auth middleware;
2. fixed-window limiter;
3. `express.json({ limit: config.jsonLimit })`;
4. MCP route.

Generate an internal request ID with `crypto.randomUUID()`. Log only:
```ts
logger.info('mcp request completed', {
  requestId,
  method: req.method,
  statusCode: res.statusCode,
  durationMs,
});
```

Do not trust or log an inbound request ID without normalization.

- [ ] **Step 4: Make logger container-native**

Change `logger.ts` so absence of `--logs-dir` means Console transport in all environments. File transports are opt-in only. Remove the production default `/app/logs`.

In `index.ts`, replace raw `provided arguments: ...` logging with sanitized fields:
```ts
logger.info('starting dockerhub MCP server', {
  transport: config.transport,
  port: config.port,
});
```

- [ ] **Step 5: Verify GREEN and no leakage**
```powershell
npm.cmd test
npm.cmd run lint
npm.cmd run format:check
```

- [ ] **Step 6: Commit**
```bash
git add src/server.ts src/index.ts src/logger.ts test/server-http.test.mjs
git commit -m "feat: harden MCP HTTP transport"
```

---

### Task 4: Make the image reproducible and reduce the attack surface

**Files:**
- Modify: Dockerfile
- Modify: package-lock.json only if Linux npm ci proves the existing lock incomplete

- [ ] **Step 1: Record the Node 24 Alpine digest**
```powershell
docker pull node:24-alpine
docker image inspect node:24-alpine --format '{{index .RepoDigests 0}}'
```

- [ ] **Step 2: Replace current image base**

Use the exact recorded digest for both builder and runtime stages. Remove `npm install --package-lock-only` from the image build. Build must consume the committed lockfile with `npm ci`.

Use `COPY --chown=appuser:appgroup` where possible instead of a full recursive `chown` layer.

- [ ] **Step 3: Prove npm ci works on Linux**
```powershell
docker build --no-cache -t fesio-mcp:hardening .
```
If Linux-only lock data is actually missing, regenerate the lock once inside Node 24 Linux, inspect the diff, and commit only the justified lock changes.

- [ ] **Step 4: Scan before accepting**
```powershell
docker scout quickview fesio-mcp:hardening
docker scout cves fesio-mcp:hardening
```
Do not call the image secure merely because counts fall; record reachable runtime findings for Task 7.

- [ ] **Step 5: Commit**
```bash
git add Dockerfile package-lock.json
git commit -m "build: pin hardened Node 24 MCP image"
```

---

### Task 5: Persist the complete runtime as a Docker Compose project

**Files:**
- Create: compose.yaml
- Create: .env.example
- Modify: .gitignore

**Compose requirements:**
```yaml
name: fesio-mcp

services:
  mcp:
    build:
      context: .
    image: fesio-mcp:1.1.0
    restart: unless-stopped
    command: ["--transport=http", "--port=3000"]
    ports:
      - "127.0.0.1:3000:3000"
    environment:
      NODE_ENV: production
      MCP_AUTH_TOKEN_FILE: /run/secrets/mcp_auth_token
      MCP_RATE_LIMIT_PER_MINUTE: ${MCP_RATE_LIMIT_PER_MINUTE:-60}
      MCP_JSON_LIMIT: ${MCP_JSON_LIMIT:-1mb}
    secrets:
      - mcp_auth_token
    read_only: true
    tmpfs:
      - /tmp
    cap_drop:
      - ALL
    security_opt:
      - no-new-privileges:true
    healthcheck:
      test: ["CMD", "node", "-e", "fetch('http://127.0.0.1:3000/health').then(r=>{if(!r.ok)process.exit(1)}).catch(()=>process.exit(1))"]
      interval: 15s
      timeout: 5s
      retries: 5
    networks:
      - fesio-mcp-net

secrets:
  mcp_auth_token:
    file: ./.secrets/mcp_auth_token

networks:
  fesio-mcp-net:
    name: fesio-mcp-net
```

Add `.secrets/` to `.gitignore`. Do not commit the real token.

- [ ] **Step 1: Create a cryptographically random local secret without printing it**
Use Node crypto to write 32 random bytes as base64url into `.secrets/mcp_auth_token`.

- [ ] **Step 2: Validate Compose**
```powershell
docker compose config
```
Inspect output and confirm it contains no raw secret.

- [ ] **Step 3: Replace ad-hoc MCP container with Compose**
```powershell
docker rm -f fesio-mcp
docker compose up -d --build mcp
docker compose ps
```

- [ ] **Step 4: Restart verification**
```powershell
docker compose restart mcp
docker compose ps
```
Wait for healthy status and rerun authenticated MCP initialize.

- [ ] **Step 5: Commit**
```bash
git add compose.yaml .env.example .gitignore
git commit -m "ops: persist MCP runtime in Docker Compose"
```

---

### Task 6: Add CI verification for every future change

**Files:**
- Create: .github/workflows/verify.yml

Workflow uses Node 24 and runs:
```yaml
- run: npm ci
- run: npm test
- run: npm run lint
- run: npm run format:check
- run: docker build -t fesio-mcp:ci .
```

Pin GitHub Actions by commit SHA, following the repository's existing workflow style.

- [ ] **Step 1: Add workflow**
- [ ] **Step 2: Run the same commands locally**
- [ ] **Step 3: Commit**
```bash
git add .github/workflows/verify.yml
git commit -m "ci: verify MCP build tests and container"
```

---

### Task 7: Run the Fable Security evidence pass

**Files:**
- Create only if useful: docs/security/mcp-threat-model.md

**Trust boundaries to inspect:**
- Internet/Cloudflare -> cloudflared.
- cloudflared -> private Docker network.
- HTTP middleware -> MCP dispatch.
- MCP tools -> Docker Hub/Scout APIs.
- secret files -> runtime memory.
- logs -> Docker Desktop log storage.

- [ ] **Step 1: Verify no secret-like material is tracked**
Use repository searches that print filenames/line numbers but redact values.

- [ ] **Step 2: Review npm production vulnerabilities**
```powershell
npm.cmd audit --omit=dev --json
```
Classify direct vs transitive and reachable vs non-reachable. Do not blindly upgrade majors.

- [ ] **Step 3: Review Docker Scout results**
Compare old and hardened images and record remaining blocking findings.

- [ ] **Step 4: Verify attack paths**
Prove:
- unauthenticated MCP request is denied;
- oversized body cannot reach MCP;
- token/body sentinel is absent from logs;
- direct host exposure is localhost only;
- container runs non-root with dropped capabilities.

- [ ] **Step 5: Commit only evidence/docs or targeted fixes backed by tests**

---

### Task 8: Validate NORA/Brain with the Noodle Seed route

**Files:**
- No source mutation unless validation identifies a concrete issue.
- Existing entrypoint: brain/server.ts
- Existing config: noodle.json

- [ ] **Step 1: Check WSL2 Ubuntu availability**
Because Noodle Seed on Windows requires WSL2 Bash, run:
```powershell
wsl.exe --status
wsl.exe -l -v
```

- [ ] **Step 2: If WSL2 Ubuntu is available, run project validation**
Use the public Noodle lifecycle from WSL:
```bash
noodle validate --json
noodle test --json
```
If a project-local Noodle Seed skill is installed by setup/reconcile, follow it instead of inventing a parallel lifecycle.

- [ ] **Step 3: If WSL is absent**
Record Noodle validation as blocked and use the supported fallback:
```powershell
wsl --install -d Ubuntu
```
Do not claim Noodle validation passed until the actual commands run successfully.

---

### Task 9: Replace Quick Tunnel with a stable production tunnel

**Files:**
- Modify: compose.yaml
- Local only: .secrets/cloudflare_tunnel_token
- No Cloudflare token in Git or command history.

**Cloudflare facts to preserve:**
- Quick Tunnel remains development-only.
- Use a remotely-managed Named Tunnel for production.
- cloudflared >= 2025.4.0 supports `--token-file`.

Add Compose service only after a real Named Tunnel token exists:
```yaml
  cloudflared:
    image: cloudflare/cloudflared:<pinned-version>
    restart: unless-stopped
    command:
      - tunnel
      - --no-autoupdate
      - run
      - --token-file
      - /run/secrets/cloudflare_tunnel_token
    secrets:
      - cloudflare_tunnel_token
    networks:
      - fesio-mcp-net
    depends_on:
      mcp:
        condition: service_healthy
```

The Cloudflare published application must route:
`mcp.fesiomatyzacja.pro -> http://mcp:3000`.

- [ ] **Step 1: Authenticate/create the Named Tunnel**
This may require a one-time Cloudflare browser authorization. Never paste the tunnel token into chat.

- [ ] **Step 2: Choose DNS mode based on the actual Cloudflare zone**
Preferred: Full Setup with Cloudflare authoritative DNS.
Alternative: supported Partial/CNAME setup while OVH remains authoritative; create the provider-specific CNAME target Cloudflare instructs for that partial zone. Do not point an arbitrary external CNAME directly at `<UUID>.cfargotunnel.com` unless Cloudflare confirms that mode for this account.

- [ ] **Step 3: Store tunnel token as Docker secret file**
Write `.secrets/cloudflare_tunnel_token` locally without printing it.

- [ ] **Step 4: Start the complete Compose stack**
```powershell
docker compose up -d --build
docker compose ps
```

- [ ] **Step 5: Verify public DNS and MCP**
Confirm `mcp.fesiomatyzacja.pro` resolves through the configured Cloudflare route and run authenticated MCP initialize over HTTPS.

- [ ] **Step 6: Remove the temporary Quick Tunnel**
Delete `fesio-mcp-tunnel` only after the stable hostname passes the public handshake.

- [ ] **Step 7: Commit Compose tunnel configuration**
No secrets included.

---

### Task 10: Final verification and release evidence

**Files:**
- No new feature code.
- Optional: docs/verification/2026-09-22-mcp-hardening.md

Run fresh, in this order:
```powershell
npm.cmd ci
npm.cmd test
npm.cmd run lint
npm.cmd run format:check
npm.cmd run build
docker compose config
docker compose build --no-cache
docker compose up -d
docker compose ps
docker scout quickview fesio-mcp:1.1.0
```

Then verify:
1. `GET http://127.0.0.1:3000/health` -> 200.
2. `GET /readiness` -> 200.
3. unauthenticated `POST /mcp` -> 401.
4. authenticated local initialize -> 200.
5. authenticated `https://mcp.fesiomatyzacja.pro/mcp` initialize -> 200.
6. `docker inspect` shows non-root/read-only/no-new-privileges/cap-drop configuration.
7. `docker logs` contains startup/request metadata but no request body/token sentinel.
8. `git status --short` is empty.
9. branch is pushed and GitHub checks are inspected.

Only after all nine checks have fresh evidence:
- remove any obsolete ad-hoc container/network not owned by Compose;
- keep one canonical MCP runtime project in Docker Desktop;
- open/merge the branch according to repository policy.

## Execution method
The user's standing instruction is to perform the work end-to-end, so execute this plan natively in the current session after plan approval, task by task, using red-green-refactor for behavior changes and fresh verification before every completion claim.
