import { zodResolver } from "@hookform/resolvers/zod";
import type { ReactElement } from "react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { z } from "zod";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { safeRedirectPath } from "../auth/redirect";
import { Alert } from "../components/Alert";
import { IconTile } from "../components/Badges";
import { BrandMark, Icon, type IconName } from "../components/icons";
import { Spinner } from "../components/Spinner";

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
    <main className="grid min-h-screen lg:grid-cols-[1.1fr_1fr]">
      <IntroPanel />
      <div className="flex flex-col justify-center px-6 py-16 sm:px-12">
        <div className="mx-auto w-full max-w-sm animate-fade-rise">
          <div className="mb-8 flex items-center gap-2.5 font-display text-xl font-bold tracking-tight lg:hidden">
            <BrandMark />
            <span>
              Proof<span className="text-brand">Chain</span>
            </span>
          </div>
          <h1 className="page-title">Login</h1>
          <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
            Sign in to submit, approve and verify documents.
          </p>
          <form
            className="mt-8 space-y-5"
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
                className="mt-1.5 w-full px-3.5 py-3"
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
                className="mt-1.5 w-full px-3.5 py-3"
                {...register("password")}
              />
              {errors.password && (
                <p className="mt-1 text-sm text-red-600 dark:text-red-400">
                  {errors.password.message}
                </p>
              )}
            </div>
            {formError && <Alert>{formError}</Alert>}
            <button
              type="submit"
              disabled={isSubmitting}
              className="btn-primary w-full py-3 text-base"
            >
              {isSubmitting && <Spinner />}
              {isSubmitting ? "Signing in�" : "Sign in"}
            </button>
          </form>
          <p className="mt-6 text-sm text-gray-500 dark:text-gray-400">
            No account?{" "}
            <Link to="/register" className="link">
              Register
            </Link>
          </p>
          <p className="mt-3 text-sm">
            <Link to="/verify" className="link inline-flex items-center gap-1">
              Verify a document without signing in
              <Icon name="arrowRight" className="h-3.5 w-3.5" />
            </Link>
          </p>
        </div>
      </div>
    </main>
  );
}

const BUILT_WITH = ["FastAPI", "MongoDB", "Solidity", "React", "NLP"];

const FEATURES: { icon: IconName; title: string; body: string }[] = [
  {
    icon: "fingerprint",
    title: "Tamper detection",
    body: "Cryptographic hashes and Merkle roots decide whether a file matches an approved version.",
  },
  {
    icon: "layers",
    title: "Change localization",
    body: "Highlights the exact region that differs and labels it (amount, party, obligation, clause removed).",
  },
  {
    icon: "link",
    title: "On-chain proof",
    body: "Every approved version is anchored on Ethereum, so records can't be quietly rewritten.",
  },
];

function IntroPanel(): ReactElement {
  return (
    <section
      aria-labelledby="intro-title"
      className="hero !rounded-none flex flex-col justify-center gap-8 border-0 px-6 py-12 sm:px-12 lg:min-h-screen lg:px-16"
    >
      <div className="relative flex flex-col gap-3">
        <div className="mb-3 hidden items-center gap-2.5 lg:flex">
          <BrandMark className="h-11 w-11" />
        </div>
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-blue-600 dark:text-blue-300">
          Document provenance
        </p>
        <h2
          id="intro-title"
          className="font-display text-5xl font-bold tracking-tight text-gray-900 dark:text-white"
        >
          Proof<span className="text-brand">Chain</span>
        </h2>
        <p className="max-w-md text-lg text-gray-600 dark:text-gray-300">
          Prove a document is genuine, and see exactly what changed if it isn&apos;t.
        </p>
      </div>
      <ol className="relative flex max-w-md flex-col gap-5">
        {FEATURES.map((f) => (
          <li key={f.title} className="flex items-start gap-3.5">
            <IconTile name={f.icon} className="h-10 w-10" />
            <div>
              <h3 className="text-[15px] font-bold text-gray-900 dark:text-white">{f.title}</h3>
              <p className="text-sm text-gray-600 dark:text-gray-400">{f.body}</p>
            </div>
          </li>
        ))}
      </ol>
      <p className="relative text-[13px] text-gray-500 dark:text-gray-400">
        Crypto decides the verdict. AI only explains it.
      </p>
      <ul className="relative flex flex-wrap gap-2" aria-label="Built with">
        {BUILT_WITH.map((tech) => (
          <li key={tech} className="badge badge-accent">
            {tech}
          </li>
        ))}
      </ul>
    </section>
  );
}
