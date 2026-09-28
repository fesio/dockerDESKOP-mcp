import assert from 'node:assert/strict';
import path from 'node:path';
import process from 'node:process';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

test('search accepts Docker Hardened Image results', { timeout: 45_000 }, async () => {
    const transport = new StdioClientTransport({
        command: process.execPath,
        args: [path.join(projectRoot, 'dist', 'index.js'), '--transport=stdio'],
        env: {
            ...process.env,
            NODE_USE_SYSTEM_CA: process.env.NODE_USE_SYSTEM_CA ?? '1',
        },
        stderr: 'pipe',
    });
    const client = new Client({ name: 'docker-hub-mcp-test', version: '1.0.0' });

    try {
        await client.connect(transport);
        const result = await client.callTool(
            { name: 'search', arguments: { query: 'nginx', size: 1 } },
            undefined,
            { timeout: 30_000 }
        );

        assert.notEqual(result.isError, true, JSON.stringify(result.content));
        assert.ok(Array.isArray(result.structuredContent?.results));
        assert.ok(result.structuredContent.results.length > 0);
    } finally {
        await client.close();
    }
});
