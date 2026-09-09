-- Set the tenant identity once per transaction, from trusted server-side auth claims.
BEGIN;
SELECT set_config('app.tenant_id', :'tenant_id', true);

-- Hybrid retrieval: lexical + vector. Bind :embedding as vector(1536).
WITH lexical AS (
 SELECT id,source_id,content,ts_rank_cd(content_tsv,websearch_to_tsquery('simple',:'query')) score
 FROM evo.knowledge_chunks WHERE content_tsv @@ websearch_to_tsquery('simple',:'query') ORDER BY score DESC LIMIT 30
), semantic AS (
 SELECT id,source_id,content,1-(embedding <=> :'embedding'::vector) score
 FROM evo.knowledge_chunks WHERE embedding_profile_id=:'embedding_profile_id'::uuid AND embedding IS NOT NULL
 ORDER BY embedding <=> :'embedding'::vector LIMIT 30
), combined AS (
 SELECT id,source_id,content,max(score) score FROM (SELECT * FROM lexical UNION ALL SELECT * FROM semantic) s GROUP BY id,source_id,content
) SELECT * FROM combined ORDER BY score DESC LIMIT 12;

-- Atomically lease one queued experiment job. Return null when no job is available.
SELECT * FROM evo.claim_job(:'worker_id',60);

-- Guarded champion promotion; caller must have correctness and security passes.
WITH candidate AS (
 SELECT c.* FROM evo.candidates c
 WHERE c.id=:'candidate_id'::uuid AND c.status='challenger' AND c.correctness_passed AND c.security_passed
 FOR UPDATE
), retire AS (
 UPDATE evo.candidates SET status='retired'
 WHERE experiment_id=(SELECT experiment_id FROM candidate) AND status='champion' RETURNING id
)
UPDATE evo.candidates SET status='champion' WHERE id=(SELECT id FROM candidate) RETURNING *;

-- Insert trace safely. Do not include credentials, raw authorization headers or prompt secrets.
INSERT INTO evo.mcp_traces(tenant_id,trace_id,request_id,tool_name,duration_ms,status,attributes)
VALUES (evo.current_tenant(),:'trace_id',:'request_id',:'tool_name',:duration_ms,:'status',:'attributes'::jsonb);

COMMIT;