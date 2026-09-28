/** API types mirroring docs/04_API_SPEC.md. Extended as endpoints are consumed. */

export interface ErrorEnvelope {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
}

export type Role = "ISSUER" | "APPROVER" | "VERIFIER" | "ADMIN";

export interface User {
  id: string;
  email: string;
  full_name: string;
  roles: Role[];
  is_active: boolean;
  created_at: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest {
  email: string;
  password: string;
  full_name: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: "bearer";
  user: User;
}
