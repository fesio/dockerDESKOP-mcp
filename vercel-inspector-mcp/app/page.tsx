const cardStyle = {
    maxWidth: 760,
    margin: '12vh auto',
    padding: 32,
    border: '1px solid #d4d4d8',
    borderRadius: 16,
    fontFamily: 'system-ui, sans-serif',
    lineHeight: 1.55,
} as const;

export default function HomePage() {
    return (
        <main style={cardStyle}>
            <h1>Vercel Inspector MCP</h1>
            <p>
                Read-only endpoint for deployment history, redacted build diagnostics and
                environment-variable metadata.
            </p>
            <p>
                MCP endpoint: <code>/api/mcp</code>
                <br />
                Health endpoint: <code>/api/health</code>
            </p>
        </main>
    );
}
