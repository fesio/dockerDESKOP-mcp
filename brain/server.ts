import { annotations, connector, prompt, resource, server, tool, z } from '@noodleseed/one';

const domain = z.enum([
    'programming',
    'automation',
    'research',
    'trading',
    'business',
    'writing',
    'general',
]);

const priority = z.enum(['low', 'normal', 'high', 'critical']);
const risk = z.enum(['low', 'medium', 'high']);
const memoryKind = z.enum([
    'decision',
    'lesson',
    'project',
    'reference',
    'task_result',
    'preference',
]);
const sensitivity = z.enum(['public', 'internal', 'private', 'secret']);
const projectKind = z.enum([
    'api',
    'mcp_server',
    'ai_agent',
    'web_app',
    'data_pipeline',
    'trading_strategy',
    'automation',
    'cli',
    'library',
]);
const workflowEngine = z.enum([
    'mcp_native',
    'n8n',
    'google_cloud',
    'github_actions',
    'docker',
    'hybrid',
]);
const workflowTrigger = z.enum([
    'manual',
    'webhook',
    'schedule',
    'event',
    'message',
    'file_change',
]);

const executionStep = z.object({
    id: z.string(),
    order: z.number().int(),
    worker_role: z.string(),
    executor: z.enum(['model_host', 'obsidian_bridge', 'notebooklm', 'n8n', 'docker', 'human']),
    instruction: z.string(),
    depends_on: z.array(z.string()).max(4),
    approval_required: z.boolean(),
    writes_state: z.boolean(),
});

const orchestration = connector('brain_orchestration')
    .version('1.0.0')
    .compute('plan', {
        input: z.object({
            objective: z.string().min(3).max(4000),
            domain,
            priority,
            risk,
            needs_fresh_sources: z.boolean(),
            needs_external_integrations: z.boolean(),
            needs_schedule: z.boolean(),
            remember_result: z.boolean(),
        }),
        output: z.object({
            execution_id: z.string(),
            controller: z.literal('mcp_orchestrator'),
            n8n_role: z.literal('optional_executor'),
            policy: z.string(),
            steps: z.array(executionStep).max(12),
            completion_gate: z.array(z.string()).max(5),
        }),
        run(input) {
            const normalized = input.objective.toLowerCase().replace(/\s+/g, ' ').trim();
            let hash = 2166136261;
            for (let index = 0; index < normalized.length; index += 1) {
                hash ^= normalized.charCodeAt(index);
                hash = Math.imul(hash, 16777619);
            }

            const steps: Array<{
                id: string;
                order: number;
                worker_role: string;
                executor:
                    | 'model_host'
                    | 'obsidian_bridge'
                    | 'notebooklm'
                    | 'n8n'
                    | 'docker'
                    | 'human';
                instruction: string;
                depends_on: string[];
                approval_required: boolean;
                writes_state: boolean;
            }> = [];

            if (input.risk === 'high') {
                steps.push({
                    id: 'approve_scope',
                    order: steps.length + 1,
                    worker_role: 'human_supervisor',
                    executor: 'human',
                    instruction:
                        'Confirm the exact scope, targets and allowed side effects before execution.',
                    depends_on: [],
                    approval_required: true,
                    writes_state: false,
                });
            }

            steps.push({
                id: 'retrieve_context',
                order: steps.length + 1,
                worker_role: 'memory_retriever',
                executor: 'obsidian_bridge',
                instruction: `Retrieve only notes relevant to: ${input.objective}`,
                depends_on: input.risk === 'high' ? ['approve_scope'] : [],
                approval_required: false,
                writes_state: false,
            });

            if (input.needs_fresh_sources) {
                steps.push({
                    id: 'ground_sources',
                    order: steps.length + 1,
                    worker_role: 'source_researcher',
                    executor: 'notebooklm',
                    instruction:
                        'Ground the task in approved source documents and return claims with source references.',
                    depends_on: ['retrieve_context'],
                    approval_required: false,
                    writes_state: false,
                });
            }

            const specialistByDomain: Record<string, string> = {
                programming: 'software_engineer',
                automation: 'automation_architect',
                research: 'research_analyst',
                trading: 'quantitative_analyst',
                business: 'business_strategist',
                writing: 'technical_writer',
                general: 'general_reasoner',
            };
            const analysisDependencies = input.needs_fresh_sources
                ? ['retrieve_context', 'ground_sources']
                : ['retrieve_context'];

            steps.push({
                id: 'specialist_work',
                order: steps.length + 1,
                worker_role: specialistByDomain[input.domain] ?? 'general_reasoner',
                executor: 'model_host',
                instruction: `Produce the requested result for: ${input.objective}`,
                depends_on: analysisDependencies,
                approval_required: false,
                writes_state: false,
            });

            if (input.needs_external_integrations || input.needs_schedule) {
                steps.push({
                    id: 'integration_execution',
                    order: steps.length + 1,
                    worker_role: 'workflow_executor',
                    executor: 'n8n',
                    instruction: input.needs_schedule
                        ? 'Execute approved integration steps and register the requested schedule; return execution evidence.'
                        : 'Execute approved integration steps and return execution evidence.',
                    depends_on: ['specialist_work'],
                    approval_required: input.risk !== 'low',
                    writes_state: true,
                });
            }

            steps.push({
                id: 'critic_review',
                order: steps.length + 1,
                worker_role: 'independent_critic',
                executor: 'model_host',
                instruction:
                    'Verify correctness, evidence, security, completeness and consistency. Return concrete corrections.',
                depends_on: [
                    input.needs_external_integrations || input.needs_schedule
                        ? 'integration_execution'
                        : 'specialist_work',
                ],
                approval_required: false,
                writes_state: false,
            });

            if (input.remember_result) {
                steps.push({
                    id: 'write_memory',
                    order: steps.length + 1,
                    worker_role: 'memory_writer',
                    executor: 'obsidian_bridge',
                    instruction:
                        'Write the approved outcome, decisions, evidence and lessons to Obsidian; never store secrets.',
                    depends_on: ['critic_review'],
                    approval_required: input.risk === 'high',
                    writes_state: true,
                });
            }

            return {
                execution_id: `brain-${(hash >>> 0).toString(16).padStart(8, '0')}`,
                controller: 'mcp_orchestrator' as const,
                n8n_role: 'optional_executor' as const,
                policy: 'MCP owns planning and gates. Executors perform bounded steps and return evidence.',
                steps,
                completion_gate: [
                    'Every step returned evidence or an explicit blocker.',
                    'The critic reviewed the final result independently.',
                    'No secret was written to prompts, logs or memory.',
                    'State-changing work had the required approval.',
                ],
            };
        },
    });

const codeEngineering = connector('code_engineering')
    .version('1.0.0')
    .compute('prepare', {
        input: z.object({
            objective: z.string().min(3).max(6000),
            language: z.string().min(1).max(80),
            project_kind: projectKind,
            runtime: z.string().min(1).max(160),
            constraints: z.array(z.string().min(1).max(500)).max(12),
            integrations: z.array(z.string().min(1).max(160)).max(12),
            risk,
        }),
        output: z.object({
            language: z.string(),
            recommended_stack: z.array(z.string()).max(10),
            architecture_rules: z.array(z.string()).max(12),
            implementation_phases: z
                .array(
                    z.object({
                        id: z.string(),
                        role: z.string(),
                        goal: z.string(),
                        deliverables: z.array(z.string()).max(6),
                        depends_on: z.array(z.string()).max(4),
                    })
                )
                .max(10),
            test_gates: z.array(z.string()).max(12),
            security_gates: z.array(z.string()).max(10),
            definition_of_done: z.array(z.string()).max(10),
        }),
        run(input) {
            const language = input.language.trim();
            const key = language.toLowerCase();
            const stacks: Record<string, string[]> = {
                python: [
                    'Python 3.12+',
                    'uv or Poetry',
                    'Ruff',
                    'mypy',
                    'pytest',
                    'FastAPI for HTTP APIs',
                ],
                typescript: [
                    'TypeScript strict mode',
                    'Node.js 22+',
                    'ESLint',
                    'Prettier',
                    'Vitest',
                    'Zod at trust boundaries',
                ],
                javascript: [
                    'Node.js 22+',
                    'ES modules',
                    'ESLint',
                    'Prettier',
                    'Vitest',
                    'JSDoc or generated declarations',
                ],
                go: [
                    'Current stable Go',
                    'go fmt',
                    'go vet',
                    'staticcheck',
                    'testing',
                    'golangci-lint',
                ],
                rust: [
                    'Current stable Rust',
                    'Cargo workspaces',
                    'rustfmt',
                    'Clippy',
                    'cargo test',
                    'cargo audit',
                ],
                'c++': [
                    'C++20 or newer',
                    'CMake',
                    'clang-format',
                    'clang-tidy',
                    'Catch2 or GoogleTest',
                    'sanitizers',
                ],
                'c#': [
                    'Current .NET LTS',
                    'nullable reference types',
                    'dotnet format',
                    'xUnit',
                    'Roslyn analyzers',
                ],
                java: [
                    'Current Java LTS',
                    'Gradle or Maven',
                    'SpotBugs',
                    'Checkstyle',
                    'JUnit 5',
                    'Testcontainers',
                ],
                sql: [
                    'Versioned migrations',
                    'SQLFluff',
                    'transactional tests',
                    'query plans',
                    'least-privilege roles',
                ],
                bash: [
                    'Bash strict mode',
                    'ShellCheck',
                    'shfmt',
                    'Bats',
                    'explicit error handling',
                ],
                powershell: [
                    'PowerShell 7+',
                    'PSScriptAnalyzer',
                    'Pester',
                    'ShouldProcess for changes',
                ],
                'pine script': [
                    'Pine Script v6',
                    'non-repainting signals',
                    'commission and slippage',
                    'walk-forward validation',
                    'alert contracts',
                ],
                mql5: [
                    'MQL5 strict mode',
                    'Strategy Tester',
                    'forward testing',
                    'risk limits',
                    'broker constraint handling',
                ],
            };
            const recommendedStack = stacks[key] ?? [
                `Current stable ${language} toolchain`,
                'Official formatter and linter',
                'Deterministic unit-test framework',
                'Dependency and vulnerability scanning',
                'Reproducible build configuration',
            ];
            const phases = [
                {
                    id: 'contract',
                    role: 'solution_architect',
                    goal: `Turn the objective into typed boundaries, acceptance criteria and explicit non-goals for ${input.project_kind}.`,
                    deliverables: ['requirements.md', 'interface contracts', 'threat model'],
                    depends_on: [],
                },
                {
                    id: 'implementation',
                    role: 'senior_software_engineer',
                    goal: `Implement the smallest complete solution in ${language} for runtime ${input.runtime}.`,
                    deliverables: [
                        'production source',
                        'configuration schema',
                        'actionable errors',
                    ],
                    depends_on: ['contract'],
                },
                {
                    id: 'verification',
                    role: 'test_engineer',
                    goal: 'Prove normal, boundary, failure and recovery paths with deterministic tests.',
                    deliverables: [
                        'unit tests',
                        'integration tests',
                        'negative tests',
                        'verification report',
                    ],
                    depends_on: ['implementation'],
                },
                {
                    id: 'critic',
                    role: 'independent_code_reviewer',
                    goal: 'Review correctness, maintainability, security, performance and operational readiness; require concrete fixes.',
                    deliverables: ['review findings', 'resolved findings', 'residual risks'],
                    depends_on: ['verification'],
                },
                {
                    id: 'delivery',
                    role: 'release_engineer',
                    goal: 'Package reproducibly with documentation, observability and rollback instructions.',
                    deliverables: ['build artifact', 'runbook', 'release notes'],
                    depends_on: ['critic'],
                },
            ];
            const testGates = [
                'Formatter and linter pass with no suppressed errors.',
                'Static type checks pass at the strictest practical level.',
                'Unit tests cover business rules and edge cases.',
                'Integration tests verify every external boundary with controlled fixtures.',
                'Failure, timeout, retry and idempotency behavior is tested.',
                'The build is reproducible from a clean environment.',
            ];
            if (input.project_kind === 'trading_strategy') {
                testGates.push(
                    'Backtests include fees, slippage, out-of-sample data and explicit anti-overfitting checks.'
                );
                testGates.push(
                    'Live-trading actions remain disabled until paper and forward-testing gates pass.'
                );
            }
            if (input.integrations.length > 0) {
                testGates.push(
                    'Integration contracts are tested without logging credentials or sensitive payloads.'
                );
            }
            const securityGates = [
                'Validate all untrusted input at the boundary and reject unknown fields where practical.',
                'Use least privilege and keep secrets outside source, prompts, logs and generated artifacts.',
                'Separate read-only planning from state-changing execution and require approval for risky writes.',
                'Pin or lock dependencies and scan them for known vulnerabilities.',
                'Use structured, redacted logs with correlation identifiers and no sensitive values.',
                'Document rollback, data retention and recovery behavior.',
            ];
            if (input.risk === 'high')
                securityGates.push(
                    'Require human approval before every external or irreversible action.'
                );
            return {
                language,
                recommended_stack: recommendedStack.slice(0, 10),
                architecture_rules: [
                    'Keep domain logic independent from transports, frameworks and external providers.',
                    'Use explicit typed contracts at every process, network and persistence boundary.',
                    'Prefer small composable modules with dependency injection over hidden global state.',
                    'Make retries bounded, observable and safe through idempotency.',
                    'Treat configuration as validated data and fail fast on invalid settings.',
                    'Provide structured errors that state the cause, retryability and recovery action.',
                    `Preserve these constraints: ${input.constraints.join('; ') || 'none supplied'}.`,
                    `Integrate only through explicit adapters: ${input.integrations.join(', ') || 'no external integrations supplied'}.`,
                ],
                implementation_phases: phases,
                test_gates: testGates.slice(0, 12),
                security_gates: securityGates.slice(0, 10),
                definition_of_done: [
                    'Acceptance criteria are mapped to passing evidence.',
                    'No placeholder, TODO, mock-only path or silent fallback remains in production flow.',
                    'The independent critic has no unresolved critical or high finding.',
                    'Setup, operation, monitoring and rollback are documented.',
                    'Generated code is complete, internally consistent and ready for a clean build.',
                ],
            };
        },
    });

const workflowEngineering = connector('workflow_engineering')
    .version('1.0.0')
    .compute('design', {
        input: z.object({
            objective: z.string().min(3).max(6000),
            engine: workflowEngine,
            trigger: workflowTrigger,
            integrations: z.array(z.string().min(1).max(160)).max(12),
            expected_frequency: z.string().min(1).max(160),
            risk,
            human_approval: z.boolean(),
            persist_result: z.boolean(),
        }),
        output: z.object({
            controller: z.literal('mcp_orchestrator'),
            engine: z.string(),
            n8n_role: z.literal('optional_executor'),
            nodes: z
                .array(
                    z.object({
                        id: z.string(),
                        type: z.string(),
                        purpose: z.string(),
                        depends_on: z.array(z.string()).max(4),
                        retry_policy: z.string(),
                        evidence: z.string(),
                    })
                )
                .max(12),
            controls: z.array(z.string()).max(12),
            observability: z.array(z.string()).max(10),
            acceptance_tests: z.array(z.string()).max(10),
        }),
        run(input) {
            const nodes: Array<{
                id: string;
                type: string;
                purpose: string;
                depends_on: string[];
                retry_policy: string;
                evidence: string;
            }> = [
                {
                    id: 'trigger',
                    type: input.trigger,
                    purpose: `Start the workflow at ${input.expected_frequency} and attach a correlation id.`,
                    depends_on: [],
                    retry_policy: 'Do not retry trigger delivery blindly; deduplicate by event id.',
                    evidence: 'accepted event id and timestamp',
                },
                {
                    id: 'validate',
                    type: 'policy_gate',
                    purpose:
                        'Validate input schema, authorization, scope, freshness and duplicate status.',
                    depends_on: ['trigger'],
                    retry_policy: 'No retry for invalid input; return an actionable rejection.',
                    evidence: 'validated normalized input or explicit rejection',
                },
                {
                    id: 'context',
                    type: 'knowledge_read',
                    purpose: `Retrieve the minimum Obsidian and approved source context needed for: ${input.objective}`,
                    depends_on: ['validate'],
                    retry_policy:
                        'Two bounded retries, then continue only when missing context is non-critical.',
                    evidence: 'source references and retrieval status',
                },
                {
                    id: 'specialist',
                    type: 'model_worker',
                    purpose: 'Produce a typed proposal; do not perform external writes.',
                    depends_on: ['context'],
                    retry_policy: 'One repair attempt using validation findings.',
                    evidence: 'typed proposal and assumptions',
                },
                {
                    id: 'critic',
                    type: 'independent_review',
                    purpose:
                        'Check correctness, security, completeness, unsupported claims and policy compliance.',
                    depends_on: ['specialist'],
                    retry_policy:
                        'Return to specialist once for concrete repair; otherwise stop blocked.',
                    evidence: 'review verdict and resolved findings',
                },
            ];
            let executionDependency = 'critic';
            if (input.human_approval || input.risk !== 'low') {
                nodes.push({
                    id: 'approval',
                    type: 'human_gate',
                    purpose:
                        'Approve the exact prepared action, target and side effects before execution.',
                    depends_on: ['critic'],
                    retry_policy: 'Never retry or infer approval.',
                    evidence: 'approval decision bound to the prepared action',
                });
                executionDependency = 'approval';
            }
            nodes.push({
                id: 'execute',
                type:
                    input.engine === 'n8n' || input.engine === 'hybrid'
                        ? 'n8n_executor'
                        : `${input.engine}_executor`,
                purpose: `Execute bounded adapters for: ${input.integrations.join(', ') || 'the selected internal operation'}. MCP retains orchestration authority.`,
                depends_on: [executionDependency],
                retry_policy:
                    'Exponential backoff with jitter, a strict attempt limit and idempotency key.',
                evidence: 'per-operation status, identifiers and sanitized errors',
            });
            if (input.persist_result) {
                nodes.push({
                    id: 'persist',
                    type: 'obsidian_memory',
                    purpose: 'Write the approved result, evidence and lessons without secrets.',
                    depends_on: ['execute'],
                    retry_policy:
                        'Retry only when the write is idempotent; preserve the same record key.',
                    evidence: 'memory path and content checksum',
                });
            }
            nodes.push({
                id: 'complete',
                type: 'completion_gate',
                purpose:
                    'Finish only when all required evidence exists; otherwise expose the first blocker.',
                depends_on: [input.persist_result ? 'persist' : 'execute'],
                retry_policy: 'No automatic retry; resume from the first failed node.',
                evidence: 'final status, duration, changed targets and residual risks',
            });
            return {
                controller: 'mcp_orchestrator' as const,
                engine: input.engine,
                n8n_role: 'optional_executor' as const,
                nodes,
                controls: [
                    'MCP owns routing, dependencies, model selection and the completion gate.',
                    'n8n may execute integrations or schedules but never decides task completion.',
                    'Every external write is isolated from read-only preparation and explicitly annotated.',
                    'Inputs and outputs use versioned schemas; incompatible versions fail closed.',
                    'Each event has an idempotency key and each retry has a strict limit.',
                    'Secrets are referenced by managed names and never copied into workflow definitions.',
                    'Concurrency, rate limits, timeouts and circuit breaking are explicit per adapter.',
                    'A dead-letter path retains sanitized failure context for controlled replay.',
                ],
                observability: [
                    'Structured logs: execution_id, node_id, attempt, duration_ms, status and error_code.',
                    'Metrics: starts, successes, failures, retries, dead letters and end-to-end latency.',
                    'Traces propagate the same correlation id through MCP, models, n8n and adapters.',
                    'Alerts distinguish transient failures, permanent failures and policy denials.',
                    'Audit records identify approvals and changed targets without storing secret values.',
                ],
                acceptance_tests: [
                    'A valid event completes once and produces all declared evidence.',
                    'A duplicate event produces no duplicate side effect.',
                    'Invalid input fails before any external operation.',
                    'A transient dependency failure follows bounded retry and recovery policy.',
                    'A permanent failure enters the dead-letter path with an actionable error.',
                    'A risky write cannot run without approval bound to the exact prepared action.',
                    'Logs, traces and stored memory contain no credentials or sensitive payloads.',
                ],
            };
        },
    });

const coverage = connector('programming_coverage')
    .version('1.0.0')
    .compute('audit', {
        input: z.object({
            known_languages: z.array(z.string().min(1).max(80)).max(200),
            focus: z.enum(['core', 'extended', 'ai', 'trading', 'all']),
        }),
        output: z.object({
            focus: z.string(),
            expected_count: z.number().int(),
            covered_count: z.number().int(),
            coverage_percent: z.number(),
            missing_languages: z.array(z.string()).max(100),
            next_action: z.string(),
        }),
        run(input) {
            const core = [
                'C',
                'C++',
                'C#',
                'Go',
                'Java',
                'JavaScript',
                'Kotlin',
                'PHP',
                'Python',
                'Ruby',
                'Rust',
                'Swift',
                'TypeScript',
                'SQL',
                'Bash',
                'PowerShell',
            ];
            const extended = [
                'Ada',
                'Assembly',
                'Clojure',
                'COBOL',
                'Crystal',
                'D',
                'Dart',
                'Delphi',
                'Elixir',
                'Elm',
                'Erlang',
                'F#',
                'Fortran',
                'Groovy',
                'Haskell',
                'Julia',
                'Lua',
                'MATLAB',
                'Nim',
                'Objective-C',
                'OCaml',
                'Perl',
                'R',
                'Racket',
                'Scala',
                'Scheme',
                'Smalltalk',
                'Solidity',
                'V',
                'Visual Basic',
                'Zig',
            ];
            const ai = [
                'Python',
                'Julia',
                'R',
                'C++',
                'CUDA',
                'Mojo',
                'MATLAB',
                'Wolfram Language',
                'Prolog',
                'Lisp',
            ];
            const trading = [
                'Pine Script',
                'MQL4',
                'MQL5',
                'EasyLanguage',
                'AFL',
                'Python',
                'R',
                'C#',
                'C++',
                'JavaScript',
            ];
            let expected = core;
            if (input.focus === 'extended') expected = extended;
            if (input.focus === 'ai') expected = ai;
            if (input.focus === 'trading') expected = trading;
            if (input.focus === 'all') expected = core.concat(extended, ai, trading);
            const uniqueExpected: string[] = [];
            for (let index = 0; index < expected.length; index += 1) {
                if (uniqueExpected.indexOf(expected[index]) === -1)
                    uniqueExpected.push(expected[index]);
            }
            const missing: string[] = [];
            for (let index = 0; index < uniqueExpected.length; index += 1) {
                const candidate = uniqueExpected[index];
                let found = false;
                for (
                    let knownIndex = 0;
                    knownIndex < input.known_languages.length;
                    knownIndex += 1
                ) {
                    if (input.known_languages[knownIndex].toLowerCase() === candidate.toLowerCase())
                        found = true;
                }
                if (!found) missing.push(candidate);
            }
            const covered = uniqueExpected.length - missing.length;
            return {
                focus: input.focus,
                expected_count: uniqueExpected.length,
                covered_count: covered,
                coverage_percent:
                    uniqueExpected.length === 0
                        ? 100
                        : Math.round((covered / uniqueExpected.length) * 10000) / 100,
                missing_languages: missing.slice(0, 100),
                next_action:
                    missing.length === 0
                        ? 'Audit frameworks, versions, testing, security and tooling for every covered language.'
                        : 'Create one Obsidian language profile per missing entry, then rerun the audit.',
            };
        },
    });

const memory = connector('memory_preparation')
    .version('1.0.0')
    .compute('prepare', {
        input: z.object({
            title: z.string().min(1).max(160),
            summary: z.string().min(1).max(8000),
            kind: memoryKind,
            tags: z.array(z.string().min(1).max(50)).max(12),
            source: z.string().min(1).max(300),
            confidence: z.number().min(0).max(1),
            sensitivity,
            send_to_notebooklm: z.boolean(),
        }),
        output: z.object({
            relative_path: z.string(),
            markdown: z.string(),
            drive_sync: z.boolean(),
            notebooklm_eligible: z.boolean(),
            blocked_reason: z.string(),
        }),
        run(input) {
            let slug = input.title
                .toLowerCase()
                .replace(/[^a-z0-9]+/g, '-')
                .slice(0, 80);
            if (slug.length === 0) slug = 'memory';
            const safeTags: string[] = [];
            for (let index = 0; index < input.tags.length && index < 12; index += 1) {
                const tag = input.tags[index].toLowerCase().replace(/[^a-z0-9_-]+/g, '-');
                if (tag.length > 0) safeTags.push(tag);
            }
            const notebooklmEligible =
                input.send_to_notebooklm &&
                input.sensitivity !== 'private' &&
                input.sensitivity !== 'secret';
            const relativePath = `Brain/${input.kind}/${slug}.md`;
            const markdown = [
                '---',
                `kind: ${input.kind}`,
                `confidence: ${input.confidence}`,
                `sensitivity: ${input.sensitivity}`,
                `source: ${input.source.replace(/\n/g, ' ')}`,
                `tags: [${safeTags.join(', ')}]`,
                '---',
                '',
                `# ${input.title}`,
                '',
                input.summary,
            ].join('\n');
            return {
                relative_path: relativePath,
                markdown,
                drive_sync: input.sensitivity !== 'secret',
                notebooklm_eligible: notebooklmEligible,
                blocked_reason:
                    input.send_to_notebooklm && !notebooklmEligible
                        ? 'Private and secret memories cannot be sent to NotebookLM.'
                        : '',
            };
        },
    });

const languageCatalog = [
    { name: 'Python', category: 'general_ai', priority: 'critical' },
    { name: 'TypeScript', category: 'web_agents', priority: 'critical' },
    { name: 'JavaScript', category: 'web_automation', priority: 'critical' },
    { name: 'SQL', category: 'data', priority: 'critical' },
    { name: 'Pine Script', category: 'trading', priority: 'critical' },
    { name: 'MQL4', category: 'trading', priority: 'high' },
    { name: 'MQL5', category: 'trading', priority: 'high' },
    { name: 'C++', category: 'systems_quant', priority: 'high' },
    { name: 'Rust', category: 'systems', priority: 'high' },
    { name: 'Go', category: 'cloud_services', priority: 'high' },
    { name: 'Bash', category: 'automation', priority: 'high' },
    { name: 'PowerShell', category: 'windows_automation', priority: 'high' },
] as const;

export default server(
    'fesiomatyzacja_brain',
    {
        title: 'Fesiomatyzacja Brain Orchestrator',
        version: '1.0.0',
        instructions:
            'Act as the control plane. Plan and gate work, delegate bounded commands to logical worker roles, demand evidence, run an independent critic, and write approved results to Obsidian memory. n8n is an optional executor, never the controller.',
        use: {
            orchestration,
            code_engineering: codeEngineering,
            workflow_engineering: workflowEngineering,
            coverage,
            memory,
        },
        context: { defaults: { locale: 'pl-PL', timeZone: 'Europe/Warsaw' } },
    },
    [
        tool('get_brain_context', {
            title: 'Pokaż architekturę mózgu',
            description:
                'Return the control-plane rules, memory roles and executor boundaries before planning work.',
            contextProvider: true,
            annotations: annotations.readOnly(),
            input: z.object({}),
            output: z.object({
                controller: z.string(),
                source_of_truth: z.string(),
                semantic_index: z.string(),
                durable_sync: z.string(),
                research_layer: z.string(),
                executors: z.array(z.string()).max(8),
                rules: z.array(z.string()).max(8),
            }),
            fulfil: () => ({
                controller: 'MCP Brain Orchestrator',
                source_of_truth: 'Obsidian Markdown vault',
                semantic_index: 'LanceDB through the local Obsidian bridge',
                durable_sync: 'Google Drive for approved non-secret knowledge',
                research_layer: 'NotebookLM for curated source-grounded work',
                executors: [
                    'model_host',
                    'obsidian_bridge',
                    'notebooklm',
                    'n8n',
                    'docker',
                    'human',
                ],
                rules: [
                    'MCP owns planning, routing and completion gates.',
                    'n8n handles integrations and schedules only when selected.',
                    'Workers receive the minimum relevant context.',
                    'A critic independently reviews important results.',
                    'Only approved conclusions are written to long-term memory.',
                    'Secrets never enter prompts, logs, Drive or NotebookLM.',
                ],
            }),
        }),
        tool('orchestrate_task', {
            title: 'Rozdziel zadanie między agentów',
            description:
                'Create an ordered, evidence-gated execution plan. Use this before delegating a complex task; n8n appears only when integrations or schedules are required.',
            annotations: annotations.readOnly(),
            input: z.object({
                objective: z.string().min(3).max(4000),
                domain,
                priority: priority.default('normal'),
                risk: risk.default('low'),
                needs_fresh_sources: z.boolean().default(false),
                needs_external_integrations: z.boolean().default(false),
                needs_schedule: z.boolean().default(false),
                remember_result: z.boolean().default(true),
            }),
            output: z.object({
                execution_id: z.string(),
                controller: z.literal('mcp_orchestrator'),
                n8n_role: z.literal('optional_executor'),
                policy: z.string(),
                steps: z.array(executionStep).max(12),
                completion_gate: z.array(z.string()).max(5),
            }),
            fulfil: ({ input, connectors }) => {
                const result = connectors.orchestration.plan({
                    objective: input.objective,
                    domain: input.domain,
                    priority: input.priority,
                    risk: input.risk,
                    needs_fresh_sources: input.needs_fresh_sources,
                    needs_external_integrations: input.needs_external_integrations,
                    needs_schedule: input.needs_schedule,
                    remember_result: input.remember_result,
                });
                return {
                    execution_id: result.execution_id,
                    controller: result.controller,
                    n8n_role: result.n8n_role,
                    policy: result.policy,
                    steps: result.steps,
                    completion_gate: result.completion_gate,
                };
            },
        }),
        tool('prepare_code_project', {
            title: 'Przygotuj kod klasy produkcyjnej',
            description:
                'Create a language-aware implementation contract for a complete production codebase, including architecture, phases, tests, security and definition of done. Use it before writing or substantially changing code.',
            annotations: annotations.readOnly(),
            input: z.object({
                objective: z.string().min(3).max(6000),
                language: z.string().min(1).max(80),
                project_kind: projectKind,
                runtime: z.string().min(1).max(160),
                constraints: z.array(z.string().min(1).max(500)).max(12).default([]),
                integrations: z.array(z.string().min(1).max(160)).max(12).default([]),
                risk: risk.default('low'),
            }),
            output: z.object({
                language: z.string(),
                recommended_stack: z.array(z.string()).max(10),
                architecture_rules: z.array(z.string()).max(12),
                implementation_phases: z
                    .array(
                        z.object({
                            id: z.string(),
                            role: z.string(),
                            goal: z.string(),
                            deliverables: z.array(z.string()).max(6),
                            depends_on: z.array(z.string()).max(4),
                        })
                    )
                    .max(10),
                test_gates: z.array(z.string()).max(12),
                security_gates: z.array(z.string()).max(10),
                definition_of_done: z.array(z.string()).max(10),
            }),
            fulfil: ({ input, connectors }) => {
                const result = connectors.code_engineering.prepare({
                    objective: input.objective,
                    language: input.language,
                    project_kind: input.project_kind,
                    runtime: input.runtime,
                    constraints: input.constraints,
                    integrations: input.integrations,
                    risk: input.risk,
                });
                return {
                    language: result.language,
                    recommended_stack: result.recommended_stack,
                    architecture_rules: result.architecture_rules,
                    implementation_phases: result.implementation_phases,
                    test_gates: result.test_gates,
                    security_gates: result.security_gates,
                    definition_of_done: result.definition_of_done,
                };
            },
        }),
        tool('design_workflow', {
            title: 'Zaprojektuj workflow i automatyzację',
            description:
                'Design a production workflow controlled by MCP, with typed nodes, dependencies, approval gates, retries, idempotency, observability and acceptance tests. n8n remains an optional executor.',
            annotations: annotations.readOnly(),
            input: z.object({
                objective: z.string().min(3).max(6000),
                engine: workflowEngine.default('hybrid'),
                trigger: workflowTrigger,
                integrations: z.array(z.string().min(1).max(160)).max(12).default([]),
                expected_frequency: z.string().min(1).max(160),
                risk: risk.default('low'),
                human_approval: z.boolean().default(false),
                persist_result: z.boolean().default(true),
            }),
            output: z.object({
                controller: z.literal('mcp_orchestrator'),
                engine: z.string(),
                n8n_role: z.literal('optional_executor'),
                nodes: z
                    .array(
                        z.object({
                            id: z.string(),
                            type: z.string(),
                            purpose: z.string(),
                            depends_on: z.array(z.string()).max(4),
                            retry_policy: z.string(),
                            evidence: z.string(),
                        })
                    )
                    .max(12),
                controls: z.array(z.string()).max(12),
                observability: z.array(z.string()).max(10),
                acceptance_tests: z.array(z.string()).max(10),
            }),
            fulfil: ({ input, connectors }) => {
                const result = connectors.workflow_engineering.design({
                    objective: input.objective,
                    engine: input.engine,
                    trigger: input.trigger,
                    integrations: input.integrations,
                    expected_frequency: input.expected_frequency,
                    risk: input.risk,
                    human_approval: input.human_approval,
                    persist_result: input.persist_result,
                });
                return {
                    controller: result.controller,
                    engine: result.engine,
                    n8n_role: result.n8n_role,
                    nodes: result.nodes,
                    controls: result.controls,
                    observability: result.observability,
                    acceptance_tests: result.acceptance_tests,
                };
            },
        }),
        tool('list_programming_catalog', {
            title: 'Pokaż katalog wiedzy programistycznej',
            description:
                'Return the priority programming-language catalog used to seed and audit the Obsidian knowledge base.',
            annotations: annotations.readOnly(),
            input: z.object({}),
            output: z.object({
                languages: z
                    .array(
                        z.object({
                            name: z.string(),
                            category: z.string(),
                            priority: z.string(),
                        })
                    )
                    .max(50),
                completeness_note: z.string(),
            }),
            fulfil: () => ({
                languages: [...languageCatalog],
                completeness_note:
                    'This is the operational priority catalog. audit_programming_coverage also supports an extended evolving catalog; no finite list can permanently represent every language.',
            }),
        }),
        tool('audit_programming_coverage', {
            title: 'Wykryj braki wiedzy programistycznej',
            description:
                'Compare languages already indexed from Obsidian with a selected catalog and return the missing profiles.',
            annotations: annotations.readOnly(),
            input: z.object({
                known_languages: z.array(z.string().min(1).max(80)).max(200),
                focus: z.enum(['core', 'extended', 'ai', 'trading', 'all']).default('all'),
            }),
            output: z.object({
                focus: z.string(),
                expected_count: z.number().int(),
                covered_count: z.number().int(),
                coverage_percent: z.number(),
                missing_languages: z.array(z.string()).max(100),
                next_action: z.string(),
            }),
            fulfil: ({ input, connectors }) => {
                const result = connectors.coverage.audit({
                    known_languages: input.known_languages,
                    focus: input.focus,
                });
                return {
                    focus: result.focus,
                    expected_count: result.expected_count,
                    covered_count: result.covered_count,
                    coverage_percent: result.coverage_percent,
                    missing_languages: result.missing_languages,
                    next_action: result.next_action,
                };
            },
        }),
        tool('prepare_memory_record', {
            title: 'Przygotuj zapis do Obsidiana',
            description:
                'Create a safe Markdown memory record and decide whether it may sync to Drive and NotebookLM. This prepares content; the Obsidian bridge performs the write.',
            annotations: annotations.readOnly(),
            input: z.object({
                title: z.string().min(1).max(160),
                summary: z.string().min(1).max(8000),
                kind: memoryKind,
                tags: z.array(z.string().min(1).max(50)).max(12),
                source: z.string().min(1).max(300),
                confidence: z.number().min(0).max(1),
                sensitivity,
                send_to_notebooklm: z.boolean().default(false),
            }),
            output: z.object({
                relative_path: z.string(),
                markdown: z.string(),
                drive_sync: z.boolean(),
                notebooklm_eligible: z.boolean(),
                blocked_reason: z.string(),
            }),
            fulfil: ({ input, connectors }) => {
                const result = connectors.memory.prepare({
                    title: input.title,
                    summary: input.summary,
                    kind: input.kind,
                    tags: input.tags,
                    source: input.source,
                    confidence: input.confidence,
                    sensitivity: input.sensitivity,
                    send_to_notebooklm: input.send_to_notebooklm,
                });
                return {
                    relative_path: result.relative_path,
                    markdown: result.markdown,
                    drive_sync: result.drive_sync,
                    notebooklm_eligible: result.notebooklm_eligible,
                    blocked_reason: result.blocked_reason,
                };
            },
        }),
        resource('brain_architecture', {
            uri: 'brain://architecture',
            title: 'Fesiomatyzacja Brain architecture',
            description: 'Control-plane responsibilities and integration boundaries.',
            mimeType: 'text/markdown',
            fulfil: () =>
                [
                    '# Fesiomatyzacja Brain',
                    '',
                    '- MCP Brain is the controller and owns task routing, dependencies and gates.',
                    '- Obsidian is the editable source of truth; LanceDB supplies semantic retrieval.',
                    '- Google Drive synchronizes approved non-secret documents.',
                    '- NotebookLM grounds research in curated Drive sources.',
                    '- n8n is an optional executor for webhooks, integrations and schedules.',
                    '- Model providers are replaceable workers selected by logical role.',
                ].join('\n'),
        }),
        resource('engineering_standards', {
            uri: 'brain://engineering-standards',
            title: 'Production engineering standards',
            description:
                'Authoritative standards for code, workflow and automation work delegated by the Brain.',
            mimeType: 'text/markdown',
            fulfil: () =>
                [
                    '# Production engineering standards',
                    '',
                    '## Code',
                    '- Start from typed contracts, acceptance criteria, non-goals and a threat model.',
                    '- Keep domain logic separate from transports, frameworks and providers.',
                    '- Generate complete files with strict validation, actionable errors and no hidden global state.',
                    '- Require formatting, linting, static analysis, unit, integration, negative and recovery tests.',
                    '- Finish with an independent critic and resolve every critical or high finding.',
                    '',
                    '## Workflows and automations',
                    '- MCP owns orchestration, dependencies, model selection and completion gates.',
                    '- n8n, Google Cloud, GitHub Actions and Docker are bounded executors, not controllers.',
                    '- Separate preparation from writes; risky writes require approval bound to the exact action.',
                    '- Every trigger is deduplicated and every write is idempotent where possible.',
                    '- Use bounded retries, circuit breakers, dead-letter handling, structured logs, metrics and traces.',
                    '',
                    '## Security and memory',
                    '- Apply least privilege and keep secrets outside code, prompts, logs and knowledge stores.',
                    '- Obsidian contains approved decisions and lessons; NotebookLM receives only curated non-private sources.',
                    '- Record evidence, changed targets, residual risks and rollback instructions.',
                ].join('\n'),
        }),
        prompt('execute_with_brain', {
            title: 'Wykonaj zadanie przez Brain Orchestrator',
            description:
                'Plan a task, execute its dependency-ordered assignments, review the result and prepare approved memory.',
            arguments: z.object({
                objective: z.string().describe('The result the user wants'),
                domain: domain.describe('Primary task domain'),
            }),
            fulfil: ({ input }) => ({
                messages: [
                    {
                        role: 'user',
                        content: {
                            type: 'text',
                            text: `Use orchestrate_task for this objective: ${input.objective}. Domain: ${input.domain}. Execute steps in dependency order, require evidence, run critic_review, and prepare memory only after approval.`,
                        },
                    },
                ],
            }),
        }),
        prompt('build_production_code', {
            title: 'Zbuduj kompletny kod produkcyjny',
            description:
                'Use the Brain engineering contract to create, verify and independently review a complete code change.',
            arguments: z.object({
                objective: z.string().describe('The software result to build'),
                language: z.string().describe('Primary implementation language'),
                project_kind: projectKind.describe('Kind of software artifact'),
                runtime: z.string().describe('Target runtime and deployment environment'),
            }),
            fulfil: ({ input }) => ({
                messages: [
                    {
                        role: 'user',
                        content: {
                            type: 'text',
                            text: `Call prepare_code_project for this objective: ${input.objective}. Language: ${input.language}. Project kind: ${input.project_kind}. Runtime: ${input.runtime}. Then implement complete production files, add deterministic tests, run the available validation gates, perform an independent critic review, repair critical and high findings, and report exact evidence plus untested layers. Never include secrets or claim checks that were not run.`,
                        },
                    },
                ],
            }),
        }),
        prompt('build_production_workflow', {
            title: 'Zbuduj kompletny workflow',
            description:
                'Design and implement a governed workflow or automation while preserving MCP as the control plane.',
            arguments: z.object({
                objective: z.string().describe('The workflow outcome'),
                engine: workflowEngine.describe('Preferred execution engine'),
                trigger: workflowTrigger.describe('Workflow trigger'),
                expected_frequency: z.string().describe('Expected run frequency or event volume'),
            }),
            fulfil: ({ input }) => ({
                messages: [
                    {
                        role: 'user',
                        content: {
                            type: 'text',
                            text: `Call design_workflow for this objective: ${input.objective}. Engine: ${input.engine}. Trigger: ${input.trigger}. Expected frequency: ${input.expected_frequency}. Implement the resulting typed nodes and contracts, keep MCP in control, treat n8n only as an optional executor, test success, duplicate, failure, retry and approval paths, and return execution evidence plus rollback instructions.`,
                        },
                    },
                ],
            }),
        }),
    ]
);
