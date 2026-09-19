/** API types mirroring docs/04_API_SPEC.md. Extended as endpoints are consumed. */

export interface ErrorEnvelope {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
}
