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
const memoryKind = z.enum(['decision', 'lesson', 'project', 'reference', 'task_result', 'preference']);
const sensitivity = z.enum(['public', 'internal', 'private', 'secret']);

const executionStep = z.object({
  id: z.string(),
  order: z.number().int(),
  worker_role: z.string(),
  executor: z.enum([
    'model_host',
    'obsidian_bridge',
    'notebooklm',
    'n8n',
    'docker',
    'human',
  ]),
  instruction: z.string(),
  depends_on: z.array(z.string()).max(4),
  approval_required: z.boolean(),
  writes_state: z.boolean(),
});

const orchestration = connector('brain_orchestration').version('1.0.0').compute('plan', {
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
      executor: 'model_host' | 'obsidian_bridge' | 'notebooklm' | 'n8n' | 'docker' | 'human';
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
        instruction: 'Confirm the exact scope, targets and allowed side effects before execution.',
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
        instruction: 'Ground the task in approved source documents and return claims with source references.',
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
      instruction: 'Verify correctness, evidence, security, completeness and consistency. Return concrete corrections.',
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
        instruction: 'Write the approved outcome, decisions, evidence and lessons to Obsidian; never store secrets.',
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

const coverage = connector('programming_coverage').version('1.0.0').compute('audit', {
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
    const core = ['C', 'C++', 'C#', 'Go', 'Java', 'JavaScript', 'Kotlin', 'PHP', 'Python', 'Ruby', 'Rust', 'Swift', 'TypeScript', 'SQL', 'Bash', 'PowerShell'];
    const extended = ['Ada', 'Assembly', 'Clojure', 'COBOL', 'Crystal', 'D', 'Dart', 'Delphi', 'Elixir', 'Elm', 'Erlang', 'F#', 'Fortran', 'Groovy', 'Haskell', 'Julia', 'Lua', 'MATLAB', 'Nim', 'Objective-C', 'OCaml', 'Perl', 'R', 'Racket', 'Scala', 'Scheme', 'Smalltalk', 'Solidity', 'V', 'Visual Basic', 'Zig'];
    const ai = ['Python', 'Julia', 'R', 'C++', 'CUDA', 'Mojo', 'MATLAB', 'Wolfram Language', 'Prolog', 'Lisp'];
    const trading = ['Pine Script', 'MQL4', 'MQL5', 'EasyLanguage', 'AFL', 'Python', 'R', 'C#', 'C++', 'JavaScript'];
    let expected = core;
    if (input.focus === 'extended') expected = extended;
    if (input.focus === 'ai') expected = ai;
    if (input.focus === 'trading') expected = trading;
    if (input.focus === 'all') expected = core.concat(extended, ai, trading);
    const uniqueExpected: string[] = [];
    for (let index = 0; index < expected.length; index += 1) {
      if (uniqueExpected.indexOf(expected[index]) === -1) uniqueExpected.push(expected[index]);
    }
    const missing: string[] = [];
    for (let index = 0; index < uniqueExpected.length; index += 1) {
      const candidate = uniqueExpected[index];
      let found = false;
      for (let knownIndex = 0; knownIndex < input.known_languages.length; knownIndex += 1) {
        if (input.known_languages[knownIndex].toLowerCase() === candidate.toLowerCase()) found = true;
      }
      if (!found) missing.push(candidate);
    }
    const covered = uniqueExpected.length - missing.length;
    return {
      focus: input.focus,
      expected_count: uniqueExpected.length,
      covered_count: covered,
      coverage_percent: uniqueExpected.length === 0 ? 100 : Math.round((covered / uniqueExpected.length) * 10000) / 100,
      missing_languages: missing.slice(0, 100),
      next_action: missing.length === 0
        ? 'Audit frameworks, versions, testing, security and tooling for every covered language.'
        : 'Create one Obsidian language profile per missing entry, then rerun the audit.',
    };
  },
});

const memory = connector('memory_preparation').version('1.0.0').compute('prepare', {
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
    let slug = input.title.toLowerCase().replace(/[^a-z0-9]+/g, '-').slice(0, 80);
    if (slug.length === 0) slug = 'memory';
    const safeTags: string[] = [];
    for (let index = 0; index < input.tags.length && index < 12; index += 1) {
      const tag = input.tags[index].toLowerCase().replace(/[^a-z0-9_-]+/g, '-');
      if (tag.length > 0) safeTags.push(tag);
    }
    const notebooklmEligible = input.send_to_notebooklm
      && input.sensitivity !== 'private'
      && input.sensitivity !== 'secret';
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
      blocked_reason: input.send_to_notebooklm && !notebooklmEligible
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
    instructions: 'Act as the control plane. Plan and gate work, delegate bounded commands to logical worker roles, demand evidence, run an independent critic, and write approved results to Obsidian memory. n8n is an optional executor, never the controller.',
    use: {
      orchestration,
      coverage,
      memory,
    },
    context: { defaults: { locale: 'pl-PL', timeZone: 'Europe/Warsaw' } },
  },
  [
    tool('get_brain_context', {
      title: 'Pokaż architekturę mózgu',
      description: 'Return the control-plane rules, memory roles and executor boundaries before planning work.',
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
        executors: ['model_host', 'obsidian_bridge', 'notebooklm', 'n8n', 'docker', 'human'],
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
      description: 'Create an ordered, evidence-gated execution plan. Use this before delegating a complex task; n8n appears only when integrations or schedules are required.',
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
    tool('list_programming_catalog', {
      title: 'Pokaż katalog wiedzy programistycznej',
      description: 'Return the priority programming-language catalog used to seed and audit the Obsidian knowledge base.',
      annotations: annotations.readOnly(),
      input: z.object({}),
      output: z.object({
        languages: z.array(z.object({
          name: z.string(),
          category: z.string(),
          priority: z.string(),
        })).max(50),
        completeness_note: z.string(),
      }),
      fulfil: () => ({
        languages: [...languageCatalog],
        completeness_note: 'This is the operational priority catalog. audit_programming_coverage also supports an extended evolving catalog; no finite list can permanently represent every language.',
      }),
    }),
    tool('audit_programming_coverage', {
      title: 'Wykryj braki wiedzy programistycznej',
      description: 'Compare languages already indexed from Obsidian with a selected catalog and return the missing profiles.',
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
      description: 'Create a safe Markdown memory record and decide whether it may sync to Drive and NotebookLM. This prepares content; the Obsidian bridge performs the write.',
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
      fulfil: () => [
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
    prompt('execute_with_brain', {
      title: 'Wykonaj zadanie przez Brain Orchestrator',
      description: 'Plan a task, execute its dependency-ordered assignments, review the result and prepare approved memory.',
      arguments: z.object({
        objective: z.string().describe('The result the user wants'),
        domain: domain.describe('Primary task domain'),
      }),
      fulfil: ({ input }) => ({
        messages: [{
          role: 'user',
          content: {
            type: 'text',
            text: `Use orchestrate_task for this objective: ${input.objective}. Domain: ${input.domain}. Execute steps in dependency order, require evidence, run critic_review, and prepare memory only after approval.`,
          },
        }],
      }),
    }),
  ],
);
