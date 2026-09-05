export const runtime = 'nodejs';

export function GET() {
    const tokenConfigured = Boolean(process.env.VERCEL_TOKEN?.trim());
    const endpointKeyConfigured = Boolean(process.env.MCP_API_KEY?.trim());
    const ready = tokenConfigured && endpointKeyConfigured;

    return Response.json(
        {
            status: ready ? 'ready' : 'misconfigured',
            checks: {
                vercel_token_configured: tokenConfigured,
                mcp_api_key_configured: endpointKeyConfigured,
            },
        },
        {
            status: ready ? 200 : 503,
            headers: { 'Cache-Control': 'no-store' },
        }
    );
}
