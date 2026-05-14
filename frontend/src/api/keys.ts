/**
 * React Query key factory for the P9a control API.
 *
 * Keys mirror the endpoint shape so `invalidateQueries({ queryKey: ['session', id] })`
 * cascades to timeline + components automatically.
 */

import type { ComponentId } from "./types";

export const qk = {
  health: () => ["health"] as const,
  system: () => ["system"] as const,
  session: (id: string) => ["session", id] as const,
  timeline: (id: string) => ["session", id, "timeline"] as const,
  component: (id: string, componentId: ComponentId) =>
    ["session", id, "component", componentId] as const,
};
