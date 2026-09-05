import { describe, expect, it } from 'vitest';
import {
    findMissingRequiredKeys,
    normalizeBuildEvents,
    normalizeDeployment,
    normalizeEnvironmentMetadata,
} from '../src/normalize';

describe('Vercel response normalization', () => {
    it('maps deployment metadata into a bounded model-facing shape', () => {
        const deployment = normalizeDeployment({
            uid: 'dpl_example',
            name: 'example-app',
            url: 'example-app.vercel.app',
            state: 'READY',
            target: 'production',
            created: 1_700_000_000_000,
            creator: { username: 'builder' },
            meta: {
                githubCommitRef: 'main',
                githubCommitSha: 'abc123',
                githubCommitMessage: 'Release',
            },
            ignoredLargeField: { nested: true },
        });

        expect(deployment).toMatchObject({
            id: 'dpl_example',
            name: 'example-app',
            url: 'https://example-app.vercel.app',
            state: 'READY',
            branch: 'main',
            commitSha: 'abc123',
        });
        expect(deployment).not.toHaveProperty('ignoredLargeField');
    });

    it('redacts and filters build errors', () => {
        const result = normalizeBuildEvents(
            [
                { type: 'stdout', created: 1_700_000_000_000, text: 'Compiling' },
                {
                    type: 'stderr',
                    created: 1_700_000_000_100,
                    text: 'Build failed token=should-not-leak',
                },
            ],
            { errorsOnly: true, limit: 10 }
        );

        expect(result.logs).toHaveLength(1);
        expect(result.logs[0]?.message).toContain('token=[REDACTED]');
        expect(JSON.stringify(result)).not.toContain('should-not-leak');
    });

    it('never copies environment variable values', () => {
        const variables = normalizeEnvironmentMetadata([
            {
                key: 'DATABASE_URL',
                target: ['production', 'preview'],
                type: 'encrypted',
                value: 'postgres://sensitive',
                decrypted: true,
                gitBranch: 'main',
            },
        ]);

        expect(variables).toEqual([
            {
                key: 'DATABASE_URL',
                targets: ['production', 'preview'],
                type: 'encrypted',
                gitBranch: 'main',
                customEnvironmentIds: [],
            },
        ]);
        expect(JSON.stringify(variables)).not.toContain('postgres://sensitive');
        expect(findMissingRequiredKeys(variables, ['DATABASE_URL', 'OPENAI_API_KEY'])).toEqual([
            'OPENAI_API_KEY',
        ]);
    });
});
