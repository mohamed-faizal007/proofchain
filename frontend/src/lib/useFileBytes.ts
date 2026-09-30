import { useCallback, useEffect, useState } from "react";

interface FileBytes {
  data: ArrayBuffer | undefined;
  isError: boolean;
  error: Error | null;
  refetch: () => Promise<void>;
}

/** Reads a local File into an ArrayBuffer (for pdf.js). No object URL is created. */
export function useFileBytes(file: File | undefined): FileBytes {
  const [state, setState] = useState<{ data?: ArrayBuffer; error: Error | null }>({ error: null });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!file) return;
    let cancelled = false;
    setState({ error: null });
    file
      .arrayBuffer()
      .then((data) => {
        if (!cancelled) setState({ data, error: null });
      })
      .catch((err: unknown) => {
        if (!cancelled) setState({ error: err instanceof Error ? err : new Error("Read failed") });
      });
    return () => {
      cancelled = true;
    };
  }, [file, attempt]);

  const refetch = useCallback(async () => setAttempt((n) => n + 1), []);
  return { data: state.data, isError: state.error !== null, error: state.error, refetch };
}
