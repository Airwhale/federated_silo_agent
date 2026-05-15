import type { ComponentId } from "./types";

export const qk = {
  health: () => ["health"] as const,
  system: () => ["system"] as const,
  session: (sessionId: string | null) => ["session", sessionId] as const,
  timeline: (sessionId: string | null) => ["session", sessionId, "timeline"] as const,
  component: (sessionId: string | null, componentId: ComponentId, instanceId?: string) =>
    ["session", sessionId, "component", componentId, instanceId ?? "global"] as const,
};
