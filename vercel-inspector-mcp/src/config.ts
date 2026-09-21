export interface AppConfig {
    vercelToken: string;
    teamId?: string;
    projectAllowlist: ReadonlySet<string>;
    requestTimeoutMs: number;
}

export class ConfigurationError extends Error {
    constructor(message: string) {
        super(message);
        this.name = 'ConfigurationError';
    }
}

function parseTimeout(raw: string | undefined): number {
    const parsed = Number(raw ?? 10_000);
    if (!Number.isFinite(parsed)) return 10_000;
    return Math.min(30_000, Math.max(1_000, Math.round(parsed)));
}

export function loadConfig(env: NodeJS.ProcessEnv = process.env): AppConfig {
    const vercelToken = env.VERCEL_TOKEN?.trim();
    if (!vercelToken) {
        throw new ConfigurationError(
            'VERCEL_TOKEN is not configured. Add it as a server-only secret and retry.'
        );
    }

    const projectAllowlist = new Set(
        (env.VERCEL_PROJECT_ALLOWLIST ?? '')
            .split(',')
            .map((entry) => entry.trim().toLowerCase())
            .filter(Boolean)
    );

    return {
        vercelToken,
        teamId: env.VERCEL_TEAM_ID?.trim() || undefined,
        projectAllowlist,
        requestTimeoutMs: parseTimeout(env.VERCEL_REQUEST_TIMEOUT_MS),
    };
}

export function assertProjectAllowed(config: AppConfig, ...candidates: unknown[]): void {
    if (config.projectAllowlist.size === 0) return;

    const normalized = candidates
        .filter((candidate): candidate is string => typeof candidate === 'string')
        .map((candidate) => candidate.trim().toLowerCase())
        .filter(Boolean);
    if (normalized.some((candidate) => config.projectAllowlist.has(candidate))) return;

    throw new ConfigurationError(
        'The requested project is outside VERCEL_PROJECT_ALLOWLIST. Update the server-side allowlist or select an allowed project.'
    );
}
