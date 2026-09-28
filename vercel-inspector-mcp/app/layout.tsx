import type { ReactNode } from 'react';

export const metadata = {
    title: 'Vercel Inspector MCP',
    description: 'Read-only, redacted Vercel deployment diagnostics for AI agents.',
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
    return (
        <html lang="pl">
            <body>{children}</body>
        </html>
    );
}
