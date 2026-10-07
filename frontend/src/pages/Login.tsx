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
    <main className="mx-auto mt-8 max-w-5xl p-6">
      <div className="card grid overflow-hidden !rounded-3xl md:grid-cols-[1.15fr_1fr]">
        <IntroPanel />
        <div className="order-first flex flex-col justify-center border-b border-gray-200 p-6 sm:p-10 md:order-none md:border-b-0 md:border-l dark:border-gray-700/70">
          <div className="mx-auto w-full max-w-sm">
            <h1 className="page-title">Login</h1>
            <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
              Sign in to submit, approve and verify documents.
            </p>
            <form
              className="mt-6 space-y-5"
              onSubmit={(e) => void handleSubmit(onSubmit)(e)}
              noValidate
            >
              <div>
                <label htmlFor="email" className="block text-sm font-medium">
                  Email
                </label>
                <input
                  id="email"
                  type="email"
                  autoComplete="username"
                  className="mt-1.5 w-full rounded border px-3 py-2.5"
                  {...register("email")}
                />
                {errors.email && (
                  <p className="mt-1 text-sm text-red-600 dark:text-red-400">
                    {errors.email.message}
                  </p>
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
                  className="mt-1.5 w-full rounded border px-3 py-2.5"
                  {...register("password")}
                />
                {errors.password && (
                  <p className="mt-1 text-sm text-red-600 dark:text-red-400">
                    {errors.password.message}
                  </p>
                )}
              </div>
              {formError && (
                <p role="alert" className="text-sm text-red-600 dark:text-red-400">
                  {formError}
                </p>
              )}
              <button type="submit" disabled={isSubmitting} className="btn-primary w-full">
                {isSubmitting ? "Signing in…" : "Sign in"}
              </button>
            </form>
            <p className="mt-4 text-sm text-gray-500 dark:text-gray-400">
              No account?{" "}
              <Link to="/register" className="underline">
                Register
              </Link>
            </p>
          </div>
        </div>
      </div>
    </main>
  );
}

const BUILT_WITH = ["FastAPI", "MongoDB", "Solidity", "React", "NLP"];

const FEATURES = [
  {
    title: "Tamper detection",
    body: "Cryptographic hashes and Merkle roots decide whether a file matches an approved version.",
  },
  {
    title: "Change localization",
    body: "Highlights the exact region that differs and labels it (amount, party, obligation, clause removed).",
  },
  {
    title: "On-chain proof",
    body: "Every approved version is anchored on Ethereum, so records can't be quietly rewritten.",
  },
];

function IntroPanel(): ReactElement {
  return (
    <section
      aria-labelledby="intro-title"
      className="flex flex-col justify-center gap-6 bg-blue-50/60 p-6 sm:p-10 dark:bg-blue-500/5"
    >
      <div className="flex flex-col gap-2">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-blue-600 dark:text-blue-300">
          Document provenance
        </p>
        <h2
          id="intro-title"
          className="font-display text-4xl font-bold tracking-tight text-gray-900 dark:text-white"
        >
          ProofChain
        </h2>
        <p className="text-lg text-gray-600 dark:text-gray-300">
          Prove a document is genuine, and see exactly what changed if it isn&apos;t.
        </p>
      </div>
      <ol className="flex flex-col gap-4">
        {FEATURES.map((f, i) => (
          <li key={f.title} className="flex items-start gap-3">
            <span
              aria-hidden="true"
              className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-blue-500/15 text-sm font-semibold text-blue-600 dark:text-blue-300"
            >
              {i + 1}
            </span>
            <div>
              <h3 className="text-[15px] font-bold text-gray-900 dark:text-white">{f.title}</h3>
              <p className="text-sm text-gray-600 dark:text-gray-400">{f.body}</p>
            </div>
          </li>
        ))}
      </ol>
      <p className="text-[13px] text-gray-500 dark:text-gray-400">
        Crypto decides the verdict. AI only explains it.
      </p>
      <ul className="flex flex-wrap gap-2" aria-label="Built with">
        {BUILT_WITH.map((tech) => (
          <li
            key={tech}
            className="rounded-full border border-blue-500/25 bg-blue-500/10 px-3 py-1 text-xs font-medium text-blue-700 dark:text-blue-100"
          >
            {tech}
          </li>
        ))}
      </ul>
    </section>
  );
}
