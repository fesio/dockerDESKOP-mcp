import { redactText } from './redact';

export interface DeploymentSummary {
    id: string;
    name: string;
    url: string;
    state: string;
    target: string;
    createdAt: string;
    creator: string;
    branch: string;
    commitSha: string;
    commitMessage: string;
    errorCode: string;
}

export interface BuildLogEntry {
    timestamp: string;
    level: string;
    message: string;
}

export interface EnvironmentVariableMetadata {
    key: string;
    targets: string[];
    type: string;
    gitBranch: string;
    customEnvironmentIds: string[];
}

function asRecord(value: unknown): Record<string, unknown> {
    return value !== null && typeof value === 'object' && !Array.isArray(value)
        ? (value as Record<string, unknown>)
        : {};
}

function toIso(value: unknown): string {
    if (typeof value !== 'number' && typeof value !== 'string') return '';
    const normalized = typeof value === 'string' && /^\d+$/.test(value) ? Number(value) : value;
    const date = new Date(normalized);
    return Number.isNaN(date.getTime()) ? '' : date.toISOString();
}

function firstString(...values: unknown[]): string {
    const value = values.find((candidate) => typeof candidate === 'string' && candidate.length > 0);
    return typeof value === 'string' ? value : '';
}

export function normalizeDeployment(value: unknown): DeploymentSummary {
    const deployment = asRecord(value);
    const meta = asRecord(deployment.meta);
    const creator = asRecord(deployment.creator);
    const rawUrl = firstString(deployment.url);

    return {
        id: String(deployment.uid ?? deployment.id ?? ''),
        name: firstString(deployment.name),
        url: rawUrl && !rawUrl.startsWith('http') ? `https://${rawUrl}` : rawUrl,
        state: String(deployment.readyState ?? deployment.state ?? deployment.status ?? 'UNKNOWN'),
        target: String(deployment.target ?? 'preview'),
        createdAt: toIso(deployment.createdAt ?? deployment.created),
        creator: firstString(creator.username, creator.githubLogin, creator.email),
        branch: firstString(meta.githubCommitRef, meta.gitlabCommitRef, meta.bitbucketCommitRef),
        commitSha: firstString(meta.githubCommitSha, meta.gitlabCommitSha, meta.bitbucketCommitSha),
        commitMessage: redactText(
            firstString(
                meta.githubCommitMessage,
                meta.gitlabCommitMessage,
                meta.bitbucketCommitMessage
            ),
            500
        ),
        errorCode: firstString(deployment.errorCode),
    };
}

export function normalizeBuildEvents(
    values: unknown[],
    options: { errorsOnly: boolean; limit: number }
): { logs: BuildLogEntry[]; matchingCount: number; truncated: boolean } {
    const normalized = values.map((value) => {
        const event = asRecord(value);
        const payload = asRecord(event.payload);
        const info = asRecord(payload.info);
        const level = String(event.type ?? payload.type ?? info.type ?? 'info').toLowerCase();
        const message = redactText(
            event.text ?? payload.text ?? info.message ?? info.name ?? '',
            2_000
        );
        const statusCode = Number(event.statusCode ?? payload.statusCode ?? 0);
        const isError =
            /error|stderr|fatal|exit|failed|failure/.test(level) ||
            statusCode >= 400 ||
            /\b(error|failed|failure|fatal|exception|exited with code [1-9])\b/i.test(message);
        return {
            timestamp: toIso(event.created ?? payload.created ?? payload.date),
            level,
            message,
            isError,
        };
    });
    const matching = normalized.filter(
        (entry) => entry.message.length > 0 && (!options.errorsOnly || entry.isError)
    );
    const logs = matching.slice(0, options.limit).map(({ timestamp, level, message }) => ({
        timestamp,
        level,
        message,
    }));
    return {
        logs,
        matchingCount: matching.length,
        truncated: matching.length > logs.length,
    };
}

export function normalizeEnvironmentMetadata(values: unknown[]): EnvironmentVariableMetadata[] {
    return values
        .map((value) => {
            const env = asRecord(value);
            const targets = Array.isArray(env.target)
                ? env.target.filter((target): target is string => typeof target === 'string')
                : typeof env.target === 'string'
                  ? [env.target]
                  : [];
            const customEnvironmentIds = Array.isArray(env.customEnvironmentIds)
                ? env.customEnvironmentIds.filter((id): id is string => typeof id === 'string')
                : typeof env.customEnvironmentId === 'string'
                  ? [env.customEnvironmentId]
                  : [];
            return {
                key: typeof env.key === 'string' ? env.key : '',
                targets: targets.slice(0, 10),
                type: typeof env.type === 'string' ? env.type : '',
                gitBranch: typeof env.gitBranch === 'string' ? env.gitBranch : '',
                customEnvironmentIds: customEnvironmentIds.slice(0, 10),
            };
        })
        .filter((entry) => entry.key.length > 0)
        .slice(0, 500);
}

export function findMissingRequiredKeys(
    variables: EnvironmentVariableMetadata[],
    requiredKeys: string[]
): string[] {
    const present = new Set(variables.map((entry) => entry.key));
    return [...new Set(requiredKeys.map((key) => key.trim()).filter(Boolean))]
        .filter((key) => !present.has(key))
        .slice(0, 100);
}

export function buildDurationMs(value: unknown): number | undefined {
    const deployment = asRecord(value);
    const start = Number(deployment.buildingAt ?? 0);
    const end = Number(deployment.ready ?? deployment.readyAt ?? 0);
    if (!Number.isFinite(start) || !Number.isFinite(end) || start <= 0 || end < start) {
        return undefined;
    }
    return Math.round(end - start);
}

export function deploymentTiming(value: unknown): { buildingAt: string; readyAt: string } {
    const deployment = asRecord(value);
    return {
        buildingAt: toIso(deployment.buildingAt),
        readyAt: toIso(deployment.ready ?? deployment.readyAt),
    };
}

export function deploymentErrorMessage(value: unknown): string {
    return redactText(asRecord(value).errorMessage ?? '', 2_000);
}
