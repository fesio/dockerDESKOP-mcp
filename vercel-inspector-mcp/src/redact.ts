const REDACTION_RULES: ReadonlyArray<readonly [RegExp, string]> = [
    [/\bBearer\s+[A-Za-z0-9._~+/-]+=*/gi, 'Bearer [REDACTED]'],
    [
        /\b(authorization|api[_-]?key|token|secret|password|passwd|cookie)\s*[:=]\s*["']?[^\s"',;]+/gi,
        '$1=[REDACTED]',
    ],
    [/\b(?:sk|vck|ghp|github_pat|vercel)_[A-Za-z0-9_-]{12,}\b/gi, '[REDACTED_TOKEN]'],
    [/\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b/g, '[REDACTED_JWT]'],
    [/([?&](?:access_token|api_key|apikey|token|secret|password)=)[^&#\s]+/gi, '$1[REDACTED]'],
];

export function redactText(value: unknown, maxLength = 2_000): string {
    let text = typeof value === 'string' ? value : '';
    for (const [pattern, replacement] of REDACTION_RULES) {
        text = text.replace(pattern, replacement);
    }
    // Log streams can contain terminal control bytes; stripping them prevents
    // terminal escape injection while preserving tabs and line breaks.
    const withoutControlCharacters = text.replace(
        // eslint-disable-next-line no-control-regex
        /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g,
        ''
    );
    return withoutControlCharacters.slice(0, Math.max(0, maxLength));
}

export function safeErrorMessage(error: unknown): string {
    if (error instanceof Error) return redactText(error.message, 1_000);
    return redactText(String(error), 1_000);
}
