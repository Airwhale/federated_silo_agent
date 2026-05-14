/**
 * Typed fetch wrapper for the P9a control API.
 *
 * Every public function returns a typed response or throws an `ApiError`
 * (`{ kind: "transport" | "http" }`). Errors preserve `detail` from FastAPI
 * verbatim so refusal reasons surface to the UI untouched.
 */

import { makeTransportError, parseHttpError, type ApiError } from "./errors";
import type {
  ComponentId,
  ComponentSnapshot,
  HealthSnapshot,
  ProbeRequest,
  ProbeResult,
  SessionCreateRequest,
  SessionSnapshot,
  SystemSnapshot,
  TimelineEventSnapshot,
} from "./types";

const BASE_URL =
  (typeof import.meta !== "undefined" && import.meta.env?.VITE_API_BASE) ||
  "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
      ...init,
    });
  } catch (err) {
    const cause = err instanceof Error ? err.message : String(err);
    const apiError: ApiError = makeTransportError(cause, err);
    throw apiError;
  }

  if (!response.ok) {
    const apiError = await parseHttpError(response);
    throw apiError;
  }

  // 204 No Content is unused today but cheap to handle.
  if (response.status === 204) {
    return undefined as unknown as T;
  }
  return (await response.json()) as T;
}

export const api = {
  health: () => request<HealthSnapshot>("/health"),

  system: () => request<SystemSnapshot>("/system"),

  createSession: (body: SessionCreateRequest = {}) =>
    request<SessionSnapshot>("/sessions", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  getSession: (sessionId: string) =>
    request<SessionSnapshot>(`/sessions/${sessionId}`),

  stepSession: (sessionId: string) =>
    request<SessionSnapshot>(`/sessions/${sessionId}/step`, { method: "POST" }),

  runUntilIdle: (sessionId: string) =>
    request<SessionSnapshot>(`/sessions/${sessionId}/run-until-idle`, { method: "POST" }),

  timeline: (sessionId: string) =>
    request<TimelineEventSnapshot[]>(`/sessions/${sessionId}/timeline`),

  component: (sessionId: string, componentId: ComponentId) =>
    request<ComponentSnapshot>(
      `/sessions/${sessionId}/components/${encodeURIComponent(componentId)}`,
    ),

  probe: (sessionId: string, body: ProbeRequest) =>
    request<ProbeResult>(`/sessions/${sessionId}/probes`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
};
