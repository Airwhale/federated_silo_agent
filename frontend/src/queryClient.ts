import { QueryClient } from "@tanstack/react-query";

/**
 * P9b query defaults. Polling is opt-in per hook via `refetchInterval`; we keep
 * `refetchIntervalInBackground=false` so a forgotten tab does not hammer the
 * local API. Stale time is short because the demo timeline is the point of the
 * console — fresh data wins over fewer requests.
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 500,
      gcTime: 5 * 60 * 1000,
      refetchOnWindowFocus: true,
      refetchIntervalInBackground: false,
      retry: 1,
    },
    mutations: {
      retry: 0,
    },
  },
});
