import type { AppConfig } from './config';
import { redactText } from './redact';

type FetchImplementation = typeof fetch;

export class VercelApiError extends Error {
    readonly status: number;
    readonly code?: string;
    readonly retryable: boolean;

    constructor(status: number, message: string, code?: string) {
        super(message);
        this.name = 'VercelApiError';
        this.status = status;
        this.code = code;
        this.retryable = status === 408 || status === 429 || status >= 500;
    }
}

function asRecord(value: unknown): Record<string, unknown> {
    return value !== null && typeof value === 'object' && !Array.isArray(value)
        ? (value as Record<string, unknown>)
        : {};
}

function parseErrorPayload(raw: string): { code?: string; message: string } {
    try {
        const body = asRecord(JSON.parse(raw));
        const error = asRecord(body.error);
        const code = typeof error.code === 'string' ? error.code : undefined;
        const message = redactText(
            error.message ?? body.message ?? 'Vercel API request failed.',
            800
        );
        return { code, message };
    } catch {
        return { message: redactText(raw || 'Vercel API request failed.', 800) };
    }
}

function parseEventStream(raw: string): unknown[] {
    if (!raw.trim()) return [];
    try {
        const parsed = JSON.parse(raw) as unknown;
        if (Array.isArray(parsed)) return parsed;
        const record = asRecord(parsed);
        return Array.isArray(record.events) ? record.events : [parsed];
    } catch {
        return raw
            .split(/\r?\n/)
            .map((line) => line.trim())
            .filter(Boolean)
            .flatMap((line) => {
                const payload = line.startsWith('data:') ? line.slice(5).trim() : line;
                try {
                    return [JSON.parse(payload) as unknown];
                } catch {
                    return [];
                }
            });
    }
}

export class VercelClient {
    private readonly apiOrigin = 'https://api.vercel.com';

    constructor(
        private readonly config: AppConfig,
        private readonly fetchImpl: FetchImplementation = fetch
    ) {}

    async listDeployments(projectIdOrName: string, limit: number): Promise<unknown[]> {
        const body = asRecord(
            await this.request('/v7/deployments', {
                projectId: projectIdOrName,
                limit: String(limit),
            })
        );
        return Array.isArray(body.deployments) ? body.deployments.slice(0, limit) : [];
    }

    async getDeployment(deploymentIdOrUrl: string): Promise<Record<string, unknown>> {
        const id = encodeURIComponent(deploymentIdOrUrl);
        return asRecord(await this.request(`/v13/deployments/${id}`));
    }

    async getBuildEvents(
        deploymentIdOrUrl: string,
        options: { limit: number; buildId?: string; direction: 'backward' | 'forward' }
    ): Promise<unknown[]> {
        const id = encodeURIComponent(deploymentIdOrUrl);
        const query: Record<string, string | undefined> = {
            direction: options.direction,
            follow: '0',
            builds: '1',
            limit: String(options.limit),
            name: options.buildId,
        };
        const response = await this.fetchResponse(`/v3/deployments/${id}/events`, query);
        const raw = await response.text();
        if (!response.ok) this.throwApiError(response.status, raw);
        return parseEventStream(raw).slice(0, options.limit);
    }

    async listEnvironmentMetadata(projectIdOrName: string): Promise<unknown[]> {
        const project = encodeURIComponent(projectIdOrName);
        const body = asRecord(
            await this.request(`/v10/projects/${project}/env`, {
                decrypt: 'false',
                source: 'fesiomatyzacja_mcp',
            })
        );
        return Array.isArray(body.envs) ? body.envs.slice(0, 500) : [];
    }

    private async request(
        path: string,
        query: Record<string, string | undefined> = {}
    ): Promise<unknown> {
        const response = await this.fetchResponse(path, query);
        const raw = await response.text();
        if (!response.ok) this.throwApiError(response.status, raw);
        if (!raw.trim()) return {};
        try {
            return JSON.parse(raw) as unknown;
        } catch {
            throw new VercelApiError(
                502,
                'Vercel API returned a non-JSON response for a JSON endpoint.'
            );
        }
    }

    private async fetchResponse(
        path: string,
        query: Record<string, string | undefined>
    ): Promise<Response> {
        const url = new URL(path, this.apiOrigin);
        for (const [key, value] of Object.entries(query)) {
            if (value) url.searchParams.set(key, value);
        }
        if (this.config.teamId) url.searchParams.set('teamId', this.config.teamId);

        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), this.config.requestTimeoutMs);
        try {
            return await this.fetchImpl(url, {
                method: 'GET',
                headers: {
                    Authorization: `Bearer ${this.config.vercelToken}`,
                    Accept: 'application/json, application/stream+json',
                    'User-Agent': 'fesiomatyzacja-vercel-inspector-mcp/1.0.0',
                },
                cache: 'no-store',
                signal: controller.signal,
            });
        } catch (error) {
            if (controller.signal.aborted) {
                throw new VercelApiError(408, 'Vercel API request timed out.');
            }
            throw error;
        } finally {
            clearTimeout(timeout);
        }
    }

    private throwApiError(status: number, raw: string): never {
        const parsed = parseErrorPayload(raw);
        throw new VercelApiError(status, parsed.message, parsed.code);
    }
}
