import { describe, expect, it, vi } from 'vitest';
import type { AppConfig } from '../src/config';
import { VercelApiError, VercelClient } from '../src/vercel-client';

const config: AppConfig = {
    vercelToken: 'unit-test-placeholder',
    teamId: 'team_example',
    projectAllowlist: new Set(),
    requestTimeoutMs: 5_000,
};

describe('VercelClient', () => {
    it('uses the current deployment endpoint and applies team scope', async () => {
        const fetchMock = vi.fn(async () =>
            Response.json({ deployments: [{ uid: 'dpl_one' }] })
        ) as unknown as typeof fetch;
        const client = new VercelClient(config, fetchMock);

        await expect(client.listDeployments('example-app', 5)).resolves.toEqual([
            { uid: 'dpl_one' },
        ]);

        const [url, init] = vi.mocked(fetchMock).mock.calls[0] ?? [];
        expect(String(url)).toContain('/v7/deployments');
        expect(String(url)).toContain('projectId=example-app');
        expect(String(url)).toContain('teamId=team_example');
        expect((init?.headers as Record<string, string>).Authorization).toBe(
            'Bearer unit-test-placeholder'
        );
    });

    it('parses bounded NDJSON build events', async () => {
        const fetchMock = vi.fn(
            async () =>
                new Response('{"type":"stdout","text":"one"}\n{"type":"stderr","text":"two"}\n')
        ) as unknown as typeof fetch;
        const client = new VercelClient(config, fetchMock);

        const events = await client.getBuildEvents('dpl_example', {
            limit: 1,
            direction: 'backward',
        });

        expect(events).toEqual([{ type: 'stdout', text: 'one' }]);
        const [url] = vi.mocked(fetchMock).mock.calls[0] ?? [];
        expect(String(url)).toContain('/v3/deployments/dpl_example/events');
        expect(String(url)).toContain('follow=0');
    });

    it('sanitizes upstream error messages', async () => {
        const fetchMock = vi.fn(async () =>
            Response.json(
                { error: { code: 'forbidden', message: 'token=must-not-leak denied' } },
                { status: 403 }
            )
        ) as unknown as typeof fetch;
        const client = new VercelClient(config, fetchMock);

        try {
            await client.getDeployment('dpl_denied');
            throw new Error('Expected the request to fail.');
        } catch (error) {
            expect(error).toBeInstanceOf(VercelApiError);
            expect((error as VercelApiError).status).toBe(403);
            expect((error as Error).message).toContain('token=[REDACTED]');
            expect((error as Error).message).not.toContain('must-not-leak');
        }
    });
});
