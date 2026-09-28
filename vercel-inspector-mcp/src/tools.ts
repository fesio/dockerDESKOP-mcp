import type { McpServer } from '@modelcontextprotocol/server';
import { z } from 'zod';
import { assertProjectAllowed, loadConfig } from './config';
import {
    buildDurationMs,
    deploymentErrorMessage,
    deploymentTiming,
    findMissingRequiredKeys,
    normalizeBuildEvents,
    normalizeDeployment,
    normalizeEnvironmentMetadata,
} from './normalize';
import { safeErrorMessage } from './redact';
import { VercelApiError, VercelClient } from './vercel-client';

const readOnlyAnnotations = {
    readOnlyHint: true,
    destructiveHint: false,
    idempotentHint: true,
    openWorldHint: true,
} as const;

const deploymentSchema = z.object({
    id: z.string(),
    name: z.string(),
    url: z.string(),
    state: z.string(),
    target: z.string(),
    createdAt: z.string(),
    creator: z.string(),
    branch: z.string(),
    commitSha: z.string(),
    commitMessage: z.string(),
    errorCode: z.string(),
});

const logSchema = z.object({
    timestamp: z.string(),
    level: z.string(),
    message: z.string(),
});

const environmentMetadataSchema = z.object({
    key: z.string(),
    targets: z.array(z.string()).max(10),
    type: z.string(),
    gitBranch: z.string(),
    customEnvironmentIds: z.array(z.string()).max(10),
});

function success(payload: Record<string, unknown>) {
    return {
        content: [{ type: 'text' as const, text: JSON.stringify(payload, null, 2) }],
        structuredContent: payload,
    };
}

function failure(error: unknown) {
    const payload = {
        error: safeErrorMessage(error),
        retryable: error instanceof VercelApiError ? error.retryable : false,
        status: error instanceof VercelApiError ? error.status : undefined,
        code: error instanceof VercelApiError ? error.code : undefined,
        nextAction:
            error instanceof VercelApiError && error.status === 401
                ? 'Replace or re-authorize VERCEL_TOKEN, then retry.'
                : error instanceof VercelApiError && error.status === 403
                  ? 'Grant the token read access to the configured team/project, then retry.'
                  : 'Verify the project/deployment identifier and server-side configuration before retrying.',
    };
    return {
        content: [{ type: 'text' as const, text: JSON.stringify(payload, null, 2) }],
        isError: true,
    };
}

export function registerVercelTools(server: McpServer): void {
    server.registerTool(
        'get_deployment_history',
        {
            title: 'Get Vercel deployment history',
            description:
                'Return recent deployments for one allowed Vercel project with state, target and Git metadata. Use this first to resolve a deployment ID before requesting logs.',
            inputSchema: z.object({
                projectIdOrName: z.string().min(1).max(160),
                limit: z.number().int().min(1).max(20).default(5),
            }),
            outputSchema: z.object({
                project: z.string(),
                deploymentCount: z.number().int(),
                deployments: z.array(deploymentSchema).max(20),
            }),
            annotations: readOnlyAnnotations,
        },
        async ({ projectIdOrName, limit }) => {
            try {
                const config = loadConfig();
                assertProjectAllowed(config, projectIdOrName);
                const raw = await new VercelClient(config).listDeployments(projectIdOrName, limit);
                const deployments = raw.map(normalizeDeployment).slice(0, limit);
                return success({
                    project: projectIdOrName,
                    deploymentCount: deployments.length,
                    deployments,
                });
            } catch (error) {
                return failure(error);
            }
        }
    );

    server.registerTool(
        'get_deployment_logs',
        {
            title: 'Diagnose a Vercel deployment',
            description:
                'Return bounded, redacted build logs plus deployment details and the next diagnostic action. Pass an ID or URL returned by get_deployment_history.',
            inputSchema: z.object({
                deploymentIdOrUrl: z.string().min(1).max(512),
                buildId: z.string().min(1).max(160).optional(),
                errorsOnly: z.boolean().default(true),
                direction: z.enum(['backward', 'forward']).default('backward'),
                limit: z.number().int().min(1).max(200).default(100),
            }),
            outputSchema: z.object({
                deployment: deploymentSchema,
                buildingAt: z.string(),
                readyAt: z.string(),
                buildDurationMs: z.number().int().nonnegative().optional(),
                errorMessage: z.string(),
                logs: z.array(logSchema).max(200),
                logCount: z.number().int(),
                logsTruncated: z.boolean(),
                diagnosis: z.string(),
                nextAction: z.string(),
                securityNote: z.string(),
            }),
            annotations: readOnlyAnnotations,
        },
        async ({ deploymentIdOrUrl, buildId, errorsOnly, direction, limit }) => {
            try {
                const config = loadConfig();
                const client = new VercelClient(config);
                const details = await client.getDeployment(deploymentIdOrUrl);
                const deployment = normalizeDeployment(details);
                assertProjectAllowed(config, deployment.name, details.projectId, details.project);
                const rawEvents = await client.getBuildEvents(deploymentIdOrUrl, {
                    limit,
                    buildId,
                    direction,
                });
                const normalizedLogs = normalizeBuildEvents(rawEvents, {
                    errorsOnly,
                    limit,
                });
                const timing = deploymentTiming(details);
                const errorMessage = deploymentErrorMessage(details);
                const firstError = normalizedLogs.logs[0]?.message || errorMessage;
                const needsRepair =
                    deployment.state === 'ERROR' ||
                    normalizedLogs.logs.length > 0 ||
                    errorMessage.length > 0;
                const inProgress = ['BUILDING', 'QUEUED', 'INITIALIZING'].includes(
                    deployment.state
                );
                const diagnosis = needsRepair
                    ? `Deployment ${deployment.id} requires attention. ${
                          firstError
                              ? `First observed error: ${firstError}`
                              : 'No textual error was returned.'
                      }`
                    : deployment.state === 'READY'
                      ? 'Deployment is READY and no matching build error was returned.'
                      : `Deployment state is ${deployment.state}; no matching build error was returned.`;
                const nextAction = needsRepair
                    ? 'Fix the first reproducible build error, run the same build locally, create a new preview deployment, and repeat this diagnostic.'
                    : inProgress
                      ? 'Wait until the deployment reaches a terminal state, then run this diagnostic again.'
                      : 'Verify the application health endpoint and runtime error logs before promoting the deployment.';

                return success({
                    deployment,
                    buildingAt: timing.buildingAt,
                    readyAt: timing.readyAt,
                    buildDurationMs: buildDurationMs(details),
                    errorMessage,
                    logs: normalizedLogs.logs,
                    logCount: normalizedLogs.logs.length,
                    logsTruncated: normalizedLogs.truncated,
                    diagnosis,
                    nextAction,
                    securityNote:
                        'Only selected event text is returned. Common bearer tokens, API keys, passwords, cookies, query credentials and JWTs are redacted; raw event payloads are never exposed.',
                });
            } catch (error) {
                return failure(error);
            }
        }
    );

    server.registerTool(
        'get_project_env_list',
        {
            title: 'Audit Vercel environment-variable metadata',
            description:
                'List only variable names, targets and non-secret metadata for one allowed project, then identify required names that are missing. Values are never requested or returned.',
            inputSchema: z.object({
                projectIdOrName: z.string().min(1).max(160),
                requiredKeys: z.array(z.string().min(1).max(160)).max(100).default([]),
            }),
            outputSchema: z.object({
                project: z.string(),
                variableCount: z.number().int(),
                variables: z.array(environmentMetadataSchema).max(500),
                missingRequiredKeys: z.array(z.string()).max(100),
                securityNote: z.string(),
            }),
            annotations: readOnlyAnnotations,
        },
        async ({ projectIdOrName, requiredKeys }) => {
            try {
                const config = loadConfig();
                assertProjectAllowed(config, projectIdOrName);
                const raw = await new VercelClient(config).listEnvironmentMetadata(projectIdOrName);
                const variables = normalizeEnvironmentMetadata(raw);
                return success({
                    project: projectIdOrName,
                    variableCount: variables.length,
                    variables,
                    missingRequiredKeys: findMissingRequiredKeys(variables, requiredKeys),
                    securityNote:
                        'The API call forces decrypt=false. Only key, target, type, branch and custom-environment IDs survive normalization; value-shaped fields are discarded.',
                });
            } catch (error) {
                return failure(error);
            }
        }
    );
}
