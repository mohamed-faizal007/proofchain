import { zodResolver } from "@hookform/resolvers/zod";
import type { ReactElement } from "react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { z } from "zod";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { safeRedirectPath } from "../auth/redirect";

const schema = z.object({
  email: z.string().min(1, "Email is required"),
  password: z.string().min(1, "Password is required"),
});

type FormValues = z.infer<typeof schema>;

export function Login(): ReactElement {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  const onSubmit = async (values: FormValues): Promise<void> => {
    setFormError(null);
    try {
      await login(values);
      const from = (location.state as { from?: string } | null)?.from;
      navigate(safeRedirectPath(from), { replace: true });
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Login failed. Please try again.");
    }
  };

  return (
    <main className="mx-auto mt-16 max-w-sm p-6">
      <h1 className="text-2xl font-semibold">Login</h1>
      <form className="mt-6 space-y-4" onSubmit={(e) => void handleSubmit(onSubmit)(e)} noValidate>
        <div>
          <label htmlFor="email" className="block text-sm font-medium">
            Email
          </label>
          <input
            id="email"
            type="email"
            autoComplete="username"
            className="mt-1 w-full rounded border px-3 py-2"
            {...register("email")}
          />
          {errors.email && (
            <p className="mt-1 text-sm text-red-600 dark:text-red-400">{errors.email.message}</p>
          )}
        </div>
        <div>
          <label htmlFor="password" className="block text-sm font-medium">
            Password
          </label>
          <input
            id="password"
            type="password"
            autoComplete="current-password"
            className="mt-1 w-full rounded border px-3 py-2"
            {...register("password")}
          />
          {errors.password && (
            <p className="mt-1 text-sm text-red-600 dark:text-red-400">{errors.password.message}</p>
          )}
        </div>
        {formError && (
          <p role="alert" className="text-sm text-red-600 dark:text-red-400">
            {formError}
          </p>
        )}
        <button
          type="submit"
          disabled={isSubmitting}
          className="w-full rounded bg-gray-900 px-4 py-2 text-white disabled:opacity-50 dark:bg-gray-100 dark:text-gray-900"
        >
          {isSubmitting ? "Signing in…" : "Sign in"}
        </button>
      </form>
      <p className="mt-4 text-sm text-gray-500 dark:text-gray-400">
        No account?{" "}
        <Link to="/register" className="underline">
          Register
        </Link>
      </p>
    </main>
  );
}
