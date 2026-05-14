/**
 * Honest error surfacing for the P9a control API.
 *
 * Two failure modes:
 *
 *   1. **Transport** — the API was unreachable. Network error, server down, CORS
 *      misconfig, etc. UI should say "API unreachable" with the underlying
 *      `message` for the developer console but not the judge.
 *   2. **HTTP** — the API replied with a non-2xx status. FastAPI returns
 *      `{ "detail": "<message>" }` for most errors; some endpoints return
 *      structured payloads (e.g. validation errors with a `detail` array).
 *      We preserve the `detail` verbatim so a refusal reason from
 *      A3/F1/P7 propagates to the UI without paraphrasing.
 *
 * `ProbeResult` failures are NOT API errors — a refused probe returns a 200
 * with `accepted=false` and `blocked_by=<layer>`. Those flow through normal
 * query data, not through this module.
 */

export type ApiError =
  | { kind: "transport"; message: string; cause?: unknown }
  | { kind: "http"; status: number; detail: string; raw?: unknown };

export function isTransportError(err: unknown): err is Extract<ApiError, { kind: "transport" }> {
  return typeof err === "object" && err !== null && (err as ApiError).kind === "transport";
}

export function isHttpError(err: unknown): err is Extract<ApiError, { kind: "http" }> {
  return typeof err === "object" && err !== null && (err as ApiError).kind === "http";
}

export function describeError(err: unknown): string {
  if (isHttpError(err)) {
    return `${err.status}: ${err.detail}`;
  }
  if (isTransportError(err)) {
    return `API unreachable — ${err.message}`;
  }
  if (err instanceof Error) {
    return err.message;
  }
  return String(err);
}

export function makeTransportError(message: string, cause?: unknown): ApiError {
  return { kind: "transport", message, cause };
}

export async function parseHttpError(response: Response): Promise<ApiError> {
  // FastAPI shape: { detail: string } for HTTPException, { detail: [...] }
  // for ValidationError. Both shapes have a `detail` field; we stringify the
  // list form so it lands in the UI as something readable.
  let raw: unknown = undefined;
  let detail = response.statusText || `HTTP ${response.status}`;
  try {
    raw = await response.json();
    if (raw && typeof raw === "object" && "detail" in raw) {
      const d = (raw as { detail: unknown }).detail;
      if (typeof d === "string") {
        detail = d;
      } else if (Array.isArray(d)) {
        detail = d
          .map((entry) => {
            if (entry && typeof entry === "object" && "msg" in entry) {
              return String((entry as { msg: unknown }).msg);
            }
            return JSON.stringify(entry);
          })
          .join("; ");
      } else {
        detail = JSON.stringify(d);
      }
    }
  } catch {
    // Body wasn't JSON; fall back to statusText.
  }
  return { kind: "http", status: response.status, detail, raw };
}
