import { createContext, useContext } from "react";
import type { ComponentId, SessionSnapshot } from "@/api/types";
import type { TrustDomain } from "@/domain/instances";

export type InspectorSelection = {
  componentId: ComponentId;
  instanceId?: TrustDomain;
};

export type SessionContextValue = {
  sessionId: string | null;
  session: SessionSnapshot | null;
  setSessionId: (sessionId: string | null) => void;
  selection: InspectorSelection | null;
  setSelection: (selection: InspectorSelection | null) => void;
};

export const SessionContext = createContext<SessionContextValue | null>(null);

export function useSessionContext() {
  const value = useContext(SessionContext);
  if (!value) {
    throw new Error("SessionContext provider is missing");
  }
  return value;
}
