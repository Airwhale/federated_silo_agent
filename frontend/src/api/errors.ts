export type ApiErrorKind = "http" | "transport";

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status?: number;
  readonly detail: string;
  readonly blockedBy?: string;
  readonly refusalReason?: string;

  constructor(input: {
    kind: ApiErrorKind;
    detail: string;
    status?: number;
    blockedBy?: string;
    refusalReason?: string;
  }) {
    super(input.detail);
    this.name = "ApiError";
    this.kind = input.kind;
    this.status = input.status;
    this.detail = input.detail;
    this.blockedBy = input.blockedBy;
    this.refusalReason = input.refusalReason;
  }
}

type ErrorBody = {
  detail?: unknown;
  blocked_by?: string;
  refusal_reason?: string;
  reason?: string;
};

export function normalizeErrorBody(status: number, body: unknown): ApiError {
  const parsed = body as ErrorBody;
  const detail =
    typeof parsed.detail === "string"
      ? parsed.detail
      : typeof parsed.reason === "string"
        ? parsed.reason
        : Array.isArray(parsed.detail)
          ? parsed.detail.map((item) => JSON.stringify(item)).join("; ")
          : `API request failed with status ${status}`;

  return new ApiError({
    kind: "http",
    status,
    detail,
    blockedBy: parsed.blocked_by,
    refusalReason: parsed.refusal_reason,
  });
}

export function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    const parts =
      error.kind === "transport"
        ? [`Transport error: ${error.detail}`]
        : [`API said no${error.status ? ` (${error.status})` : ""}: ${error.detail}`];
    if (error.blockedBy) {
      parts.push(`blocked_by=${error.blockedBy}`);
    }
    if (error.refusalReason) {
      parts.push(`refusal_reason=${error.refusalReason}`);
    }
    return parts.join(" ");
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "Unexpected UI error.";
}

export function normalizeTransportError(error: unknown): ApiError {
  if (error instanceof ApiError) {
    return error;
  }
  if (error instanceof Error) {
    return new ApiError({ kind: "transport", detail: error.message });
  }
  return new ApiError({ kind: "transport", detail: "API request failed before a response." });
}
