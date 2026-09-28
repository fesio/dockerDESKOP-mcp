import { describe, expect, it } from 'vitest';
import { redactText } from '../src/redact';

describe('redactText', () => {
    it('removes common credentials from build output', () => {
        const input = [
            'Authorization: Bearer abc.def.ghi',
            'password=hunter2',
            'api_key=super-secret-value',
            'https://example.test/?token=visible-token',
            'github_pat_abcdefghijklmnopqrstuvwxyz123456',
            'eyJabcdefgh.ijklmnop.qrstuvwx',
        ].join('\n');

        const output = redactText(input);

        expect(output).toContain('[REDACTED]');
        expect(output).not.toContain('hunter2');
        expect(output).not.toContain('super-secret-value');
        expect(output).not.toContain('visible-token');
        expect(output).not.toContain('abcdefghijklmnopqrstuvwxyz123456');
        expect(output).not.toContain('eyJabcdefgh.ijklmnop.qrstuvwx');
    });

    it('enforces an output limit', () => {
        expect(redactText('x'.repeat(100), 12)).toHaveLength(12);
    });
});
