import { createContext, useContext } from "react";

import type { ComponentId } from "@/api/types";
import type { TrustDomain } from "@/domain/instances";

/**
 * The console keeps one global "active session id" and one optional
 * "selected component / instance" for the inspector drawer. Lifted into
 * a context to avoid prop-drilling through SwimlaneTopology and friends.
 */
export interface SessionContextValue {
  sessionId: string | null;
  setSessionId: (id: string | null) => void;
  selection: { domain: TrustDomain; componentId: ComponentId } | null;
  setSelection: (sel: { domain: TrustDomain; componentId: ComponentId } | null) => void;
}

export const SessionContext = createContext<SessionContextValue | null>(null);

export function useSessionContext(): SessionContextValue {
  const ctx = useContext(SessionContext);
  if (!ctx) {
    throw new Error("SessionContext provider missing");
  }
  return ctx;
}
