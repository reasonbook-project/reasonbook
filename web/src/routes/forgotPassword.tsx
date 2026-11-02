// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { zodResolver } from "@hookform/resolvers/zod";
import { createRoute, Link } from "@tanstack/react-router";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { forgotPassword } from "@/api/auth";
import { AuthShell } from "@/components/auth/AuthShell";

import { rootRoute } from "./__root";

export const forgotPasswordRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/forgot-password",
  component: ForgotPasswordPage,
});

const schema = z.object({
  email: z.string().email("Enter a valid email address"),
});
type FormValues = z.infer<typeof schema>;

function ForgotPasswordPage() {
  const [sent, setSent] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { email: "" },
  });

  const onSubmit = async (values: FormValues) => {
    // Backend always returns 200 to prevent email enumeration. We mirror
    // that on the client: show the same confirmation regardless of whether
    // the email matched a real account.
    await forgotPassword(values.email).catch(() => undefined);
    setSent(true);
  };

  return (
    <AuthShell
      headline="Reasonbook"
      tagline="Reset your password."
    >
      {sent ? (
        <div className="space-y-4 text-center">
          <p className="text-sm text-ink-soft">
            If that email is on file, a reset link is on its way. Check your
            spam folder if it doesn&apos;t arrive within a minute.
          </p>
          <Link
            to="/login"
            className="inline-block text-sm font-medium text-navy hover:underline"
          >
            Back to sign in
          </Link>
        </div>
      ) : (
        <form onSubmit={handleSubmit(onSubmit)} noValidate className="space-y-4">
          <p className="text-sm text-ink-soft">
            Enter the email on your account and we&apos;ll send a link to set a
            new password.
          </p>

          <div>
            <label htmlFor="email" className="mb-1 block text-sm font-medium">
              Email
            </label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              autoFocus
              className="w-full rounded-md border border-rule bg-paper px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-navy"
              {...register("email")}
            />
            {errors.email && (
              <p className="mt-1 text-xs text-danger" role="alert">
                {errors.email.message}
              </p>
            )}
          </div>

          <button
            type="submit"
            disabled={isSubmitting}
            className="w-full rounded-md bg-navy px-4 py-2 text-sm font-medium text-paper transition hover:bg-navy-deep disabled:opacity-50"
          >
            {isSubmitting ? "Sending…" : "Send reset link"}
          </button>

          <p className="text-center text-xs text-ink-soft">
            Remembered it?{" "}
            <Link to="/login" className="font-medium text-navy hover:underline">
              Back to sign in
            </Link>
          </p>
        </form>
      )}
    </AuthShell>
  );
}
