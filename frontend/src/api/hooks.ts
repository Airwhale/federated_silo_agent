/**
 * TanStack Query hooks over the P9a API.
 *
 * Polling cadence:
 *   - `useTimeline` 2 s while a session is active (refetchIntervalInBackground=false)
 *   - `useSystem` 10 s for the global readiness view
 *   - `useSession` and `useComponent` rely on mutation invalidation rather than polling
 *
 * Mutations invalidate `qk.session(id)` on success so timeline + components refresh.
 * P15 swaps `useTimeline` to SSE behind this same signature.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./client";
import { qk } from "./keys";
import type {
  ComponentId,
  ProbeRequest,
  SessionCreateRequest,
} from "./types";

export function useHealth() {
  return useQuery({
    queryKey: qk.health(),
    queryFn: api.health,
    refetchInterval: 30_000,
  });
}

export function useSystem() {
  return useQuery({
    queryKey: qk.system(),
    queryFn: api.system,
    refetchInterval: 10_000,
  });
}

export function useSession(sessionId: string | null) {
  return useQuery({
    queryKey: sessionId ? qk.session(sessionId) : ["session", "none"],
    queryFn: () => api.getSession(sessionId as string),
    enabled: !!sessionId,
  });
}

export function useTimeline(sessionId: string | null) {
  return useQuery({
    queryKey: sessionId ? qk.timeline(sessionId) : ["session", "none", "timeline"],
    queryFn: () => api.timeline(sessionId as string),
    enabled: !!sessionId,
    refetchInterval: 2_000,
  });
}

export function useComponent(
  sessionId: string | null,
  componentId: ComponentId | null,
) {
  return useQuery({
    queryKey:
      sessionId && componentId
        ? qk.component(sessionId, componentId)
        : ["session", "none", "component", "none"],
    queryFn: () =>
      api.component(sessionId as string, componentId as ComponentId),
    enabled: !!sessionId && !!componentId,
  });
}

export function useCreateSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: SessionCreateRequest = {}) => api.createSession(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.system() });
    },
  });
}

export function useStepSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (sessionId: string) => api.stepSession(sessionId),
    onSuccess: (snapshot) => {
      qc.invalidateQueries({ queryKey: qk.session(snapshot.session_id) });
    },
  });
}

export function useRunUntilIdle() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (sessionId: string) => api.runUntilIdle(sessionId),
    onSuccess: (snapshot) => {
      qc.invalidateQueries({ queryKey: qk.session(snapshot.session_id) });
    },
  });
}

export function useProbe(sessionId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ProbeRequest) => {
      if (!sessionId) {
        return Promise.reject(new Error("no active session"));
      }
      return api.probe(sessionId, body);
    },
    onSuccess: () => {
      if (sessionId) {
        qc.invalidateQueries({ queryKey: qk.session(sessionId) });
      }
    },
  });
}
