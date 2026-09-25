import { useEffect, useState } from "react";
import type { ApiError } from "./api";

export type State<T> =
  | { phase: "loading" }
  | { phase: "ready"; data: T }
  | { phase: "error"; status: number; detail: string };

// Runs `load` when the component appears and again whenever `deps` change.
export function useData<T>(load: () => Promise<T>, deps: unknown[] = []): State<T> {
  const [state, setState] = useState<State<T>>({ phase: "loading" });

  useEffect(() => {
    // If `deps` change (or the component disappears) before the answer arrives, this
    // request is stale: its answer must not overwrite the newer one.
    let stale = false;
    setState({ phase: "loading" });
    load().then(
      (data) => {
        if (!stale) setState({ phase: "ready", data });
      },
      (e: ApiError) => {
        if (!stale) setState({ phase: "error", status: e.status, detail: e.detail });
      },
    );
    return () => {
      stale = true;
    };
    // `load` is not a dependency on purpose: it is a new function on every render.
  }, deps);

  return state;
}
