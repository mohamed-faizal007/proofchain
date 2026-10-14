import { createContext, useContext } from "react";

export interface ToastApi {
  notify: (message: string) => void;
}

export const ToastContext = createContext<ToastApi | null>(null);
const NOOP: ToastApi = { notify: () => undefined };

/** Outside a provider (most unit tests) notifications are silently dropped. */
export function useToast(): ToastApi {
  return useContext(ToastContext) ?? NOOP;
}
