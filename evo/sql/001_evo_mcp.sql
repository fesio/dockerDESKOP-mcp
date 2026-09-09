-- Evo MCP persistence baseline for PostgreSQL 16+ with pgvector.
-- Apply with a privileged migration role; runtime roles must use app.tenant_id.
BEGIN;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;

CREATE SCHEMA IF NOT EXISTS evo;
CREATE TYPE evo.risk_level AS ENUM ('low','medium','high','critical');
CREATE TYPE evo.approval_status AS ENUM ('pending','approved','rejected','expired');
CREATE TYPE evo.job_status AS ENUM ('queued','leased','succeeded','failed','cancelled','dead_letter');
CREATE TYPE evo.candidate_status AS ENUM ('draft','testing','rejected','challenger','champion','retired');

CREATE TABLE evo.tenants (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  slug text UNIQUE NOT NULL CHECK (slug ~ '^[a-z0-9][a-z0-9-]{1,62}$'),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE evo.embedding_profiles (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES evo.tenants(id) ON DELETE CASCADE,
  name text NOT NULL, provider text NOT NULL, model text NOT NULL,
  dimensions int NOT NULL CHECK (dimensions BETWEEN 1 AND 4096),
  metric text NOT NULL DEFAULT 'cosine' CHECK (metric IN ('cosine','l2','inner_product')),
  active boolean NOT NULL DEFAULT true, created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id,name)
);
CREATE TABLE evo.knowledge_sources (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES evo.tenants(id) ON DELETE CASCADE,
  uri text NOT NULL, content_sha256 text NOT NULL, title text,
  mime_type text, version int NOT NULL DEFAULT 1 CHECK (version > 0),
  trust_score numeric(4,3) NOT NULL DEFAULT 0.5 CHECK (trust_score BETWEEN 0 AND 1),
  sensitivity evo.risk_level NOT NULL DEFAULT 'low',
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(), superseded_at timestamptz,
  UNIQUE(tenant_id,uri,version)
);
CREATE TABLE evo.knowledge_chunks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES evo.tenants(id) ON DELETE CASCADE,
  source_id uuid NOT NULL REFERENCES evo.knowledge_sources(id) ON DELETE CASCADE,
  embedding_profile_id uuid REFERENCES evo.embedding_profiles(id),
  ordinal int NOT NULL CHECK (ordinal >= 0), content text NOT NULL,
  content_tsv tsvector GENERATED ALWAYS AS (to_tsvector('simple',content)) STORED,
  embedding vector(1536), token_count int CHECK (token_count >= 0),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb, created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(source_id,ordinal)
);
CREATE INDEX knowledge_chunks_tsv_idx ON evo.knowledge_chunks USING gin(content_tsv);
CREATE INDEX knowledge_chunks_profile_idx ON evo.knowledge_chunks(tenant_id,embedding_profile_id)
  WHERE embedding IS NOT NULL;
CREATE INDEX knowledge_chunks_embedding_hnsw ON evo.knowledge_chunks
  USING hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=64)
  WHERE embedding IS NOT NULL;

CREATE TABLE evo.model_registry (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL REFERENCES evo.tenants(id) ON DELETE CASCADE,
  provider text NOT NULL, model text NOT NULL, capabilities jsonb NOT NULL DEFAULT '[]'::jsonb,
  enabled boolean NOT NULL DEFAULT true, created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(tenant_id,provider,model)
);
CREATE TABLE evo.agent_registry (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL REFERENCES evo.tenants(id) ON DELETE CASCADE,
  name text NOT NULL, role text NOT NULL, model_id uuid REFERENCES evo.model_registry(id),
  system_prompt text NOT NULL, policy jsonb NOT NULL DEFAULT '{}'::jsonb, enabled boolean NOT NULL DEFAULT true,
  UNIQUE(tenant_id,name)
);
CREATE TABLE evo.prompt_registry (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL REFERENCES evo.tenants(id) ON DELETE CASCADE,
  name text NOT NULL, version int NOT NULL, body text NOT NULL, input_schema jsonb NOT NULL DEFAULT '{}'::jsonb,
  output_schema jsonb NOT NULL DEFAULT '{}'::jsonb, active boolean NOT NULL DEFAULT true,
  UNIQUE(tenant_id,name,version)
);
CREATE TABLE evo.mcp_registry (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL REFERENCES evo.tenants(id) ON DELETE CASCADE,
  kind text NOT NULL CHECK(kind IN ('tool','resource','prompt','extension')),
  name text NOT NULL, version text NOT NULL, manifest jsonb NOT NULL, enabled boolean NOT NULL DEFAULT true,
  UNIQUE(tenant_id,kind,name,version)
);

CREATE TABLE evo.problems (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL REFERENCES evo.tenants(id) ON DELETE CASCADE,
 name text NOT NULL, specification text NOT NULL, risk evo.risk_level NOT NULL DEFAULT 'medium',
 acceptance_contract jsonb NOT NULL DEFAULT '{}'::jsonb, created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(tenant_id,name)
);
CREATE TABLE evo.datasets (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL REFERENCES evo.tenants(id) ON DELETE CASCADE,
 name text NOT NULL, version text NOT NULL, location text NOT NULL, content_sha256 text NOT NULL,
 metadata jsonb NOT NULL DEFAULT '{}'::jsonb, UNIQUE(tenant_id,name,version)
);
CREATE TABLE evo.test_suites (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL REFERENCES evo.tenants(id) ON DELETE CASCADE,
 problem_id uuid NOT NULL REFERENCES evo.problems(id) ON DELETE CASCADE, name text NOT NULL,
 is_holdout boolean NOT NULL DEFAULT false, definition jsonb NOT NULL, UNIQUE(problem_id,name)
);
CREATE TABLE evo.experiments (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL REFERENCES evo.tenants(id) ON DELETE CASCADE,
 problem_id uuid NOT NULL REFERENCES evo.problems(id), agent_id uuid REFERENCES evo.agent_registry(id),
 status text NOT NULL DEFAULT 'planned' CHECK(status IN ('planned','running','completed','failed','cancelled')),
 budget jsonb NOT NULL DEFAULT '{}'::jsonb, started_at timestamptz, finished_at timestamptz,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE evo.candidates (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL REFERENCES evo.tenants(id) ON DELETE CASCADE,
 experiment_id uuid NOT NULL REFERENCES evo.experiments(id) ON DELETE CASCADE,
 parent_id uuid REFERENCES evo.candidates(id), lineage jsonb NOT NULL DEFAULT '{}'::jsonb,
 artifact_uri text NOT NULL, artifact_sha256 text NOT NULL, status evo.candidate_status NOT NULL DEFAULT 'draft',
 score numeric(12,6), correctness_passed boolean, security_passed boolean, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX one_champion_per_experiment ON evo.candidates(experiment_id) WHERE status='champion';
CREATE TABLE evo.evaluations (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL REFERENCES evo.tenants(id) ON DELETE CASCADE,
 candidate_id uuid NOT NULL REFERENCES evo.candidates(id) ON DELETE CASCADE,
 test_suite_id uuid REFERENCES evo.test_suites(id), verdict text NOT NULL CHECK(verdict IN ('pass','fail','error')),
 score numeric(12,6), report jsonb NOT NULL DEFAULT '{}'::jsonb, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE evo.failure_signatures (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL REFERENCES evo.tenants(id) ON DELETE CASCADE,
 signature text NOT NULL, category text NOT NULL, sample jsonb NOT NULL DEFAULT '{}'::jsonb,
 occurrences int NOT NULL DEFAULT 1, last_seen_at timestamptz NOT NULL DEFAULT now(), UNIQUE(tenant_id,signature)
);
CREATE TABLE evo.lessons (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL REFERENCES evo.tenants(id) ON DELETE CASCADE,
 problem_id uuid REFERENCES evo.problems(id), outcome text NOT NULL CHECK(outcome IN ('success','failure','neutral')),
 statement text NOT NULL, evidence jsonb NOT NULL DEFAULT '{}'::jsonb, confidence numeric(4,3) NOT NULL CHECK(confidence BETWEEN 0 AND 1),
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE evo.benchmark_runs (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL REFERENCES evo.tenants(id) ON DELETE CASCADE,
 candidate_id uuid NOT NULL REFERENCES evo.candidates(id) ON DELETE CASCADE, environment jsonb NOT NULL,
 explain_analyze jsonb, cpu_ms numeric, ram_bytes bigint, io_read_bytes bigint, io_write_bytes bigint,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE evo.autonomy_policies (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL REFERENCES evo.tenants(id) ON DELETE CASCADE,
 name text NOT NULL, max_risk evo.risk_level NOT NULL DEFAULT 'low', allowed_actions jsonb NOT NULL DEFAULT '[]'::jsonb,
 sandbox_required boolean NOT NULL DEFAULT true, active boolean NOT NULL DEFAULT true, UNIQUE(tenant_id,name)
);
CREATE TABLE evo.approval_gates (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL REFERENCES evo.tenants(id) ON DELETE CASCADE,
 action_kind text NOT NULL CHECK(action_kind IN ('ddl','production','network','deployment','secret_access')),
 target jsonb NOT NULL, requested_by text NOT NULL, status evo.approval_status NOT NULL DEFAULT 'pending',
 expires_at timestamptz, decided_by text, decision_note text, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE evo.migration_proposals (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL REFERENCES evo.tenants(id) ON DELETE CASCADE,
 ddl text NOT NULL, rollback_plan text NOT NULL, risk evo.risk_level NOT NULL, approval_id uuid REFERENCES evo.approval_gates(id),
 status text NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','approved','applied','rolled_back','rejected')),
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE evo.job_queue (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL REFERENCES evo.tenants(id) ON DELETE CASCADE,
 job_type text NOT NULL, payload jsonb NOT NULL, status evo.job_status NOT NULL DEFAULT 'queued',
 priority smallint NOT NULL DEFAULT 0, run_after timestamptz NOT NULL DEFAULT now(), attempts int NOT NULL DEFAULT 0,
 lease_owner text, lease_expires_at timestamptz, last_error text, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX job_queue_claim_idx ON evo.job_queue(priority DESC,run_after,id) WHERE status='queued';
CREATE TABLE evo.semantic_cache (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL REFERENCES evo.tenants(id) ON DELETE CASCADE,
 cache_key text NOT NULL, request_embedding vector(1536), response jsonb NOT NULL, expires_at timestamptz NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(tenant_id,cache_key)
);
CREATE TABLE evo.mcp_traces (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL REFERENCES evo.tenants(id) ON DELETE CASCADE,
 trace_id text NOT NULL, request_id text, tool_name text, duration_ms numeric, status text,
 attributes jsonb NOT NULL DEFAULT '{}'::jsonb, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE evo.human_feedback (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL REFERENCES evo.tenants(id) ON DELETE CASCADE,
 candidate_id uuid REFERENCES evo.candidates(id), rating smallint CHECK(rating BETWEEN 1 AND 5),
 comment text, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE evo.audit_log (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, tenant_id uuid REFERENCES evo.tenants(id) ON DELETE CASCADE,
 actor text NOT NULL, action text NOT NULL, entity_type text NOT NULL, entity_id text, before_data jsonb,
 after_data jsonb, trace_id text, created_at timestamptz NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION evo.current_tenant() RETURNS uuid LANGUAGE sql STABLE AS $$
 SELECT NULLIF(current_setting('app.tenant_id',true),'')::uuid $$;
DO $$ DECLARE t regclass; BEGIN
 FOR t IN SELECT c.oid::regclass FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
 WHERE n.nspname='evo' AND c.relkind='r' AND c.relname <> 'tenants' LOOP
   EXECUTE format('ALTER TABLE %s ENABLE ROW LEVEL SECURITY',t);
   EXECUTE format('CREATE POLICY tenant_isolation ON %s USING (tenant_id=evo.current_tenant()) WITH CHECK (tenant_id=evo.current_tenant())',t);
 END LOOP;
END $$;
ALTER TABLE evo.tenants ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_self ON evo.tenants USING (id=evo.current_tenant()) WITH CHECK(id=evo.current_tenant());

CREATE OR REPLACE FUNCTION evo.claim_job(p_worker text,p_lease_seconds int DEFAULT 60)
RETURNS evo.job_queue LANGUAGE plpgsql SECURITY INVOKER AS $$
DECLARE claimed evo.job_queue;
BEGIN
 WITH next_job AS (
  SELECT id FROM evo.job_queue WHERE tenant_id=evo.current_tenant() AND status='queued' AND run_after<=now()
  ORDER BY priority DESC,run_after,id FOR UPDATE SKIP LOCKED LIMIT 1
 )
 UPDATE evo.job_queue q SET status='leased',lease_owner=p_worker,lease_expires_at=now()+make_interval(secs=>p_lease_seconds),attempts=attempts+1
 FROM next_job WHERE q.id=next_job.id RETURNING q.* INTO claimed;
 RETURN claimed;
END $$;
COMMIT;