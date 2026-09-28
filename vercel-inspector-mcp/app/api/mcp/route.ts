import { createHash, timingSafeEqual } from 'node:crypto';
import { createMcpHandler } from 'mcp-handler';
import { registerVercelTools } from '../../../src/tools';

export const runtime = 'nodejs';
export const maxDuration = 60;
export const dynamic = 'force-dynamic';

const mcpHandler = createMcpHandler((server) => {
    registerVercelTools(server);
});

function digest(value: string): Buffer {
    return createHash('sha256').update(value, 'utf8').digest();
}

function bearerToken(request: Request): string | undefined {
    const authorization = request.headers.get('authorization') ?? '';
    const match = /^Bearer\s+([^\s]+)$/i.exec(authorization);
    return match?.[1];
}

async function authenticated(request: Request): Promise<Response> {
    const expected = process.env.MCP_API_KEY?.trim();
    if (!expected) {
        return Response.json(
            {
                error: 'server_misconfigured',
                message: 'MCP_API_KEY is not configured.',
            },
            { status: 503, headers: { 'Cache-Control': 'no-store' } }
        );
    }

    const supplied = bearerToken(request);
    if (!supplied || !timingSafeEqual(digest(supplied), digest(expected))) {
        return Response.json(
            { error: 'unauthorized', message: 'A valid MCP bearer credential is required.' },
            {
                status: 401,
                headers: {
                    'Cache-Control': 'no-store',
                    'WWW-Authenticate': 'Bearer realm="vercel-inspector-mcp"',
                },
            }
        );
    }

    const response = await mcpHandler(request);
    response.headers.set('Cache-Control', 'no-store');
    return response;
}

export const GET = authenticated;
export const POST = authenticated;
export const DELETE = authenticated;
