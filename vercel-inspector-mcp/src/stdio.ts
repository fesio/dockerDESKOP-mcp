import { StdioServerTransport } from '@modelcontextprotocol/server/stdio';
import { loadConfig } from './config';
import { safeErrorMessage } from './redact';
import { createVercelInspectorServer } from './server';

async function main(): Promise<void> {
    loadConfig();
    const server = createVercelInspectorServer();
    await server.connect(new StdioServerTransport());
}

main().catch((error: unknown) => {
    process.stderr.write(`Vercel Inspector MCP failed: ${safeErrorMessage(error)}\n`);
    process.exitCode = 1;
});
