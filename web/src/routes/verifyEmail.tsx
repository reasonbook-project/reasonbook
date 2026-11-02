// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { createRoute, Link, useSearch } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { z } from "zod";

import { verifyEmail } from "@/api/auth";
import { AuthShell } from "@/components/auth/AuthShell";

import { rootRoute } from "./__root";

const searchSchema = z.object({
  token: z.string().optional(),
});

export const verifyEmailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/verify-email",
  validateSearch: searchSchema,
  component: VerifyEmailPage,
});

type Status = "checking" | "ok" | "missing" | "invalid";

function VerifyEmailPage() {
  const { token } = useSearch({ from: verifyEmailRoute.id });
  const [status, setStatus] = useState<Status>("checking");

  useEffect(() => {
    if (!token) {
      setStatus("missing");
      return;
    }
    let cancelled = false;
    void verifyEmail(token)
      .then(() => {
        if (!cancelled) setStatus("ok");
      })
      .catch(() => {
        if (!cancelled) setStatus("invalid");
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  const tagline =
    status === "ok"
      ? "Email verified."
      : status === "checking"
        ? "Confirming your email…"
        : "Email verification.";

  return (
    <AuthShell
      headline="Reasonbook"
      tagline={tagline}
    >
      <div className="text-center">
        {status === "ok" && (
          <Link
            to="/inbox"
            className="inline-block text-sm font-medium text-navy hover:underline"
          >
            Continue to your inbox →
          </Link>
        )}

        {status === "missing" && (
          <p className="text-sm text-danger">
            This verification link is missing its token. Sign in and request a
            fresh verification email from your account settings.
          </p>
        )}

        {status === "invalid" && (
          <p className="text-sm text-danger">
            This link is invalid or has expired. Sign in and request a fresh
            verification email.
          </p>
        )}

        {(status === "missing" || status === "invalid") && (
          <Link
            to="/login"
            className="mt-6 inline-block text-sm font-medium text-navy hover:underline"
          >
            Back to sign in
          </Link>
        )}
      </div>
    </AuthShell>
  );
}
