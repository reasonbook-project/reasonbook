// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { zodResolver } from "@hookform/resolvers/zod";
import { createRoute, Link, useNavigate, useSearch } from "@tanstack/react-router";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { ApiError } from "@/api/client";
import { resetPassword } from "@/api/auth";
import { AuthShell } from "@/components/auth/AuthShell";

import { rootRoute } from "./__root";

const searchSchema = z.object({
  token: z.string().optional(),
});

export const resetPasswordRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/reset-password",
  validateSearch: searchSchema,
  component: ResetPasswordPage,
});

const formSchema = z
  .object({
    password: z.string().min(8, "Password must be at least 8 characters"),
    confirm: z.string(),
  })
  .refine((d) => d.password === d.confirm, {
    message: "Passwords don't match",
    path: ["confirm"],
  });
type FormValues = z.infer<typeof formSchema>;

function ResetPasswordPage() {
  const { token } = useSearch({ from: resetPasswordRoute.id });
  const navigate = useNavigate();
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: { password: "", confirm: "" },
  });

  const onSubmit = async (values: FormValues) => {
    if (!token) {
      setSubmitError(
        "This reset link is missing its token. Request a new email.",
      );
      return;
    }
    setSubmitError(null);
    try {
      await resetPassword(token, values.password);
      setDone(true);
      window.setTimeout(() => {
        void navigate({ to: "/login", replace: true });
      }, 2000);
    } catch (err) {
      if (err instanceof ApiError) {
        const body = err.body as { error?: string } | null;
        setSubmitError(body?.error ?? "Couldn't reset password.");
      } else {
        setSubmitError("Couldn't reset password.");
      }
    }
  };

  return (
    <AuthShell
      headline="Reasonbook"
      tagline="Set a new password."
    >
      {done ? (
        <p className="text-center text-sm text-ink-soft">
          Password updated. Redirecting to sign-in…
        </p>
      ) : (
        <form onSubmit={handleSubmit(onSubmit)} noValidate className="space-y-4">
          <p className="text-sm text-ink-soft">
            Pick a strong password you don&apos;t use elsewhere.
          </p>

          <div>
            <label htmlFor="password" className="mb-1 block text-sm font-medium">
              New password
            </label>
            <input
              id="password"
              type="password"
              autoComplete="new-password"
              autoFocus
              className="w-full rounded-md border border-rule bg-paper px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-navy"
              {...register("password")}
            />
            {errors.password && (
              <p className="mt-1 text-xs text-danger" role="alert">
                {errors.password.message}
              </p>
            )}
          </div>

          <div>
            <label htmlFor="confirm" className="mb-1 block text-sm font-medium">
              Confirm password
            </label>
            <input
              id="confirm"
              type="password"
              autoComplete="new-password"
              className="w-full rounded-md border border-rule bg-paper px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-navy"
              {...register("confirm")}
            />
            {errors.confirm && (
              <p className="mt-1 text-xs text-danger" role="alert">
                {errors.confirm.message}
              </p>
            )}
          </div>

          {submitError && (
            <p
              className="rounded-md bg-danger/10 px-3 py-2 text-sm text-danger"
              role="alert"
            >
              {submitError}
            </p>
          )}

          <button
            type="submit"
            disabled={isSubmitting}
            className="w-full rounded-md bg-navy px-4 py-2 text-sm font-medium text-paper transition hover:bg-navy-deep disabled:opacity-50"
          >
            {isSubmitting ? "Updating…" : "Update password"}
          </button>

          <p className="text-center text-xs text-ink-soft">
            Need a new link?{" "}
            <Link
              to="/forgot-password"
              className="font-medium text-navy hover:underline"
            >
              Request again
            </Link>
          </p>
        </form>
      )}
    </AuthShell>
  );
}
