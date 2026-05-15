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
    // Merge headers via the ``Headers`` constructor, which handles every
    // ``HeadersInit`` shape (plain object, ``Headers`` instance,
    // ``string[][]``). Spreading ``customHeaders`` into an object literal
    // would silently drop entries for the latter two shapes; this
    // utility is the single entry point for every API call, so a
    // headers-form regression would be invisible until a future caller
    // started passing a ``Headers`` instance. ``Headers.set`` after
    // construction only fills ``Content-Type`` when the caller did not
    // already specify one, so explicit overrides still win.
    const { headers: customHeaders, ...restInit } = init ?? {};
    const finalHeaders = new Headers(customHeaders);
    if (!finalHeaders.has("Content-Type")) {
      finalHeaders.set("Content-Type", "application/json");
    }
    const response = await fetch(`${API_BASE}${path}`, {
      ...restInit,
      headers: finalHeaders,
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
