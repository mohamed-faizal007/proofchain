import { zodResolver } from "@hookform/resolvers/zod";
import type { ReactElement } from "react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link } from "react-router-dom";
import { z } from "zod";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";

const schema = z.object({
  full_name: z.string().min(1, "Full name is required").max(200),
  email: z.string().min(1, "Email is required").email("Enter a valid email"),
  password: z.string().min(8, "Password must be at least 8 characters").max(256),
});

type FormValues = z.infer<typeof schema>;

export function Register(): ReactElement {
  const { register: registerUser } = useAuth();
  const [formError, setFormError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  const onSubmit = async (values: FormValues): Promise<void> => {
    setFormError(null);
    try {
      await registerUser(values);
      setSuccess(true);
    } catch (err) {
      if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
        setFormError("Registration is restricted. Ask an administrator to create your account.");
      } else if (err instanceof ApiError) {
        setFormError(err.message);
      } else {
        setFormError("Registration failed. Please try again.");
      }
    }
  };

  if (success) {
    return (
      <main className="mx-auto mt-16 max-w-sm p-6">
        <h1 className="page-title">Register</h1>
        <p className="mt-4 text-sm text-gray-600 dark:text-gray-300">
          Account created.{" "}
          <Link to="/login" className="underline">
            Sign in
          </Link>
          .
        </p>
      </main>
    );
  }

  return (
    <main className="mx-auto mt-16 max-w-sm p-6">
      <h1 className="page-title">Register</h1>
      <form className="mt-6 space-y-4" onSubmit={(e) => void handleSubmit(onSubmit)(e)} noValidate>
        <div>
          <label htmlFor="full_name" className="block text-sm font-medium">
            Full name
          </label>
          <input
            id="full_name"
            type="text"
            autoComplete="name"
            className="mt-1 w-full rounded border px-3 py-2"
            {...register("full_name")}
          />
          {errors.full_name && (
            <p className="mt-1 text-sm text-red-600 dark:text-red-400">
              {errors.full_name.message}
            </p>
          )}
        </div>
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
            autoComplete="new-password"
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
        <button type="submit" disabled={isSubmitting} className="btn-primary w-full">
          {isSubmitting ? "Creating…" : "Create account"}
        </button>
      </form>
      <p className="mt-4 text-sm text-gray-500 dark:text-gray-400">
        Already have an account?{" "}
        <Link to="/login" className="underline">
          Sign in
        </Link>
      </p>
    </main>
  );
}
