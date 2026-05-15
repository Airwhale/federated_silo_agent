import { normalizeErrorBody, normalizeTransportError } from "./errors";
import type {
  ComponentId,
  ComponentInteractionRequest,
  ComponentInteractionResult,
  ComponentSnapshot,
  HealthSnapshot,
  ProbeRequest,
  ProbeResult,
  SessionCreateRequest,
  SessionSnapshot,
  SystemSnapshot,
  TimelineEventSnapshot,
} from "./types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";
export const DEFAULT_SESSION_CREATE: SessionCreateRequest = {
  scenario_id: "s1_structuring_ring",
  mode: "stub",
};

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers ?? {}),
      },
      ...init,
    });
    const text = await response.text();
    const body = text ? JSON.parse(text) : null;
    if (!response.ok) {
      throw normalizeErrorBody(response.status, body);
    }
    return body as T;
  } catch (error) {
    throw normalizeTransportError(error);
  }
}

export const api = {
  health: () => requestJson<HealthSnapshot>("/health"),
  system: () => requestJson<SystemSnapshot>("/system"),
  createSession: (body: SessionCreateRequest = DEFAULT_SESSION_CREATE) =>
    requestJson<SessionSnapshot>("/sessions", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  session: (sessionId: string) => requestJson<SessionSnapshot>(`/sessions/${sessionId}`),
  stepSession: (sessionId: string) =>
    requestJson<SessionSnapshot>(`/sessions/${sessionId}/step`, { method: "POST" }),
  runUntilIdle: (sessionId: string) =>
    requestJson<SessionSnapshot>(`/sessions/${sessionId}/run-until-idle`, { method: "POST" }),
  timeline: (sessionId: string) =>
    requestJson<TimelineEventSnapshot[]>(`/sessions/${sessionId}/timeline`),
  events: (sessionId: string) =>
    requestJson<TimelineEventSnapshot[]>(`/sessions/${sessionId}/events`),
  component: (sessionId: string, componentId: ComponentId) =>
    requestJson<ComponentSnapshot>(`/sessions/${sessionId}/components/${componentId}`),
  probe: (sessionId: string, body: ProbeRequest) =>
    requestJson<ProbeResult>(`/sessions/${sessionId}/probes`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  interaction: (
    sessionId: string,
    componentId: ComponentId,
    body: ComponentInteractionRequest,
  ) =>
    requestJson<ComponentInteractionResult>(
      `/sessions/${sessionId}/components/${componentId}/interactions`,
      {
        method: "POST",
        body: JSON.stringify(body),
      },
    ),
};
