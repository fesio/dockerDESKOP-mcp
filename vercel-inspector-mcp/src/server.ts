import { McpServer } from '@modelcontextprotocol/server';
import { registerVercelTools } from './tools';

export function createVercelInspectorServer(): McpServer {
    const server = new McpServer({
        name: 'vercel-history-inspector',
        version: '1.0.0',
    });
    registerVercelTools(server);
    return server;
}
