# Evo MCP persistence module

This module adds a production-oriented PostgreSQL state layer to the existing MCP Brain without replacing its TypeScript MCP surface.

## What is included

- tenant-isolated knowledge sources and chunks, full-text retrieval and pgvector HNSW search;
- model, agent, prompt and MCP registries;
- experiments, candidates, test suites, evaluation gates, champion/challenger promotion, benchmark evidence, lessons and failure signatures;
- leased jobs using `FOR UPDATE SKIP LOCKED`;
- approval gates for DDL, production, network and deployment actions;
- semantic cache, traces, feedback and append-only audit records;
- RLS enforced through transaction-local `app.tenant_id`.

## Deployment prerequisites

Use PostgreSQL with the `vector` extension and a migration role that can install extensions and create policies. The runtime account must not be a superuser and should be granted only schema/table rights it needs.

The SQL uses a 1536-dimension vector column. Change every `vector(1536)` declaration before migrating if the selected embedding model uses another dimension. One database can host multiple embedding profiles, but native vector indexes require one fixed dimension per indexed column; add a separate table per dimension for mixed profiles.

## Apply

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f evo/sql/001_evo_mcp.sql
psql "$DATABASE_URL" -v tenant_id="<tenant-uuid>" -f evo/sql/queries.sql
```

## Runtime rules

1. Authenticate outside SQL, resolve a trusted tenant UUID, then execute `SET LOCAL app.tenant_id = '<uuid>'` in every transaction.
2. Never let a client set another tenant ID directly.
3. Run generated code only in a disposable sandbox. Promotion needs correctness and security evidence.
4. Bind approvals to an exact target/action and expiry. Never treat a generic approval as permission for later DDL or deployment.
5. Keep secrets out of chunks, traces, audit data and cache payloads.

## Verification

Use a disposable database to test migration rollback, RLS leakage attempts, concurrent `claim_job` calls, HNSW retrieval, and two simultaneous champion promotions. This baseline has not been executed on the user's production instance.
