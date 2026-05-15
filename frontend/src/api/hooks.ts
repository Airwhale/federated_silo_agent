import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, DEFAULT_SESSION_CREATE } from "./client";
import { qk } from "./keys";
import type {
  ComponentId,
  ComponentInteractionRequest,
  ProbeRequest,
  SessionCreateRequest,
} from "./types";

export function useHealth() {
  return useQuery({
    queryKey: qk.health(),
    queryFn: api.health,
    refetchInterval: 10000,
    refetchIntervalInBackground: false,
  });
}

export function useSystem() {
  return useQuery({
    queryKey: qk.system(),
    queryFn: api.system,
    refetchInterval: 10000,
    refetchIntervalInBackground: false,
  });
}

export function useSession(sessionId: string | null) {
  return useQuery({
    queryKey: qk.session(sessionId),
    queryFn: () => api.session(sessionId ?? ""),
    enabled: Boolean(sessionId),
  });
}

export function useTimeline(sessionId: string | null) {
  return useQuery({
    queryKey: qk.timeline(sessionId),
    queryFn: () => api.events(sessionId ?? ""),
    enabled: Boolean(sessionId),
    refetchInterval: 2000,
    refetchIntervalInBackground: false,
  });
}

export function useComponent(
  sessionId: string | null,
  componentId: ComponentId,
  instanceId?: string,
) {
  return useQuery({
    queryKey: qk.component(sessionId, componentId, instanceId),
    queryFn: () => api.component(sessionId ?? "", componentId),
    enabled: Boolean(sessionId),
  });
}

export function useCreateSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: SessionCreateRequest = DEFAULT_SESSION_CREATE) =>
      api.createSession(request),
    onSuccess: async (session) => {
      await queryClient.invalidateQueries({ queryKey: qk.system() });
      await queryClient.invalidateQueries({ queryKey: qk.session(session.session_id) });
      await queryClient.invalidateQueries({ queryKey: qk.timeline(session.session_id) });
    },
  });
}

export function useStepSession(sessionId: string | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.stepSession(sessionId ?? ""),
    onSuccess: async () => {
      if (!sessionId) return;
      await queryClient.invalidateQueries({ queryKey: ["session", sessionId] });
    },
  });
}

export function useRunUntilIdle(sessionId: string | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.runUntilIdle(sessionId ?? ""),
    onSuccess: async () => {
      if (!sessionId) return;
      await queryClient.invalidateQueries({ queryKey: ["session", sessionId] });
    },
  });
}

export function useProbe(sessionId: string | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: ProbeRequest) => api.probe(sessionId ?? "", request),
    onSuccess: async () => {
      if (!sessionId) return;
      await queryClient.invalidateQueries({ queryKey: ["session", sessionId] });
    },
  });
}

export function useInteraction(sessionId: string | null, componentId: ComponentId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: ComponentInteractionRequest) =>
      api.interaction(sessionId ?? "", componentId, request),
    onSuccess: async (_result, variables) => {
      if (!sessionId) return;
      await queryClient.invalidateQueries({ queryKey: ["session", sessionId] });
      await queryClient.invalidateQueries({
        queryKey: qk.component(sessionId, componentId, variables.target_instance_id ?? undefined),
      });
    },
  });
}
