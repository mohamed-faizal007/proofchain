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
      <div
        className="overflow-hidden rounded-3xl border border-white/10 bg-gray-950 bg-cover bg-center shadow-xl"
        style={{ backgroundImage: "url('/images/login-bg.jpg')" }}
      >
        {/* Dark overlay keeps the intro text and form readable in both themes. */}
        <div className="grid items-center gap-8 bg-gradient-to-br from-gray-950/85 via-gray-950/50 to-blue-950/25 p-6 sm:p-10 lg:grid-cols-[1.15fr_1fr]">
          <IntroPanel />
          <div className="card order-first w-full max-w-sm justify-self-center p-6 lg:order-none lg:justify-self-end">
            <h1 className="page-title">Login</h1>
            <form
              className="mt-6 space-y-4"
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
                  className="mt-1 w-full rounded border px-3 py-2"
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
                  className="mt-1 w-full rounded border px-3 py-2"
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

function IntroPanel(): ReactElement {
  return (
    <section aria-labelledby="intro-title" className="text-gray-100">
      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-blue-300">
        Document provenance
      </p>
      <h2
        id="intro-title"
        className="mt-2 font-display text-4xl font-bold tracking-tight text-white"
      >
        ProofChain
      </h2>
      <p className="mt-3 text-lg text-gray-200">
        Blockchain-anchored document provenance with AI-assisted tamper detection and localization.
      </p>
      <ul className="mt-6 space-y-4 text-sm text-gray-300">
        <li className="border-l-2 border-blue-400 pl-3">
          <span className="font-semibold text-white">What it does. </span>
          Verifies whether a document is authentic, finds if and where it was tampered with, and
          anchors proof of every approved version on-chain (Ethereum/Sepolia).
        </li>
        <li className="border-l-2 border-blue-400 pl-3">
          <span className="font-semibold text-white">Crypto decides, AI explains. </span>
          The verdict comes from hash and Merkle-root matches. AI only describes what kind of change
          happened and where, so it can never flip a verdict.
        </li>
      </ul>
      <ul className="mt-6 flex flex-wrap gap-2" aria-label="Built with">
        {BUILT_WITH.map((tech) => (
          <li
            key={tech}
            className="rounded-full border border-blue-300/30 bg-blue-400/10 px-3 py-1 text-xs font-medium text-blue-100"
          >
            {tech}
          </li>
        ))}
      </ul>
    </section>
  );
}
