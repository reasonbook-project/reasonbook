// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { zodResolver } from "@hookform/resolvers/zod";
import { createRoute, Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { ApiError } from "@/api/client";
import { login } from "@/api/auth";
import { AuthShell } from "@/components/auth/AuthShell";
import { useAuthStore } from "@/stores/auth";

import { rootRoute } from "./__root";

export const loginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/login",
  component: LoginPage,
});

const schema = z.object({
  username: z.string().min(1, "Username is required"),
  password: z.string().min(1, "Password is required"),
});
type FormValues = z.infer<typeof schema>;

function LoginPage() {
  const navigate = useNavigate();
  const setUser = useAuthStore((s) => s.setUser);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { username: "", password: "" },
  });

  const onSubmit = async (values: FormValues) => {
    setSubmitError(null);
    try {
      const user = await login(values.username, values.password);
      setUser(user);
      await navigate({ to: "/matters" });
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setSubmitError("Invalid username or password.");
      } else {
        setSubmitError("Sign-in failed. Please try again.");
      }
    }
  };

  return (
    <AuthShell
      headline="Reasonbook"
      tagline="Fraud prevention for federal & state grants."
    >
      <form onSubmit={handleSubmit(onSubmit)} noValidate className="space-y-4">
        <div>
          <label htmlFor="username" className="mb-1 block text-sm font-medium">
            Username
          </label>
          <input
            id="username"
            type="text"
            autoComplete="username"
            autoFocus
            className="w-full rounded-md border border-rule bg-paper px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-navy"
            {...register("username")}
          />
          {errors.username && (
            <p className="mt-1 text-xs text-danger" role="alert">
              {errors.username.message}
            </p>
          )}
        </div>

        <div>
          <label htmlFor="password" className="mb-1 block text-sm font-medium">
            Password
          </label>
          <input
            id="password"
            type="password"
            autoComplete="current-password"
            className="w-full rounded-md border border-rule bg-paper px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-navy"
            {...register("password")}
          />
          {errors.password && (
            <p className="mt-1 text-xs text-danger" role="alert">
              {errors.password.message}
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
          {isSubmitting ? "Signing in…" : "Sign in"}
        </button>

        <div className="flex items-center text-xs text-ink-soft">
          <Link to="/forgot-password" className="font-medium text-navy hover:underline">
            Forgot password?
          </Link>
        </div>
      </form>
    </AuthShell>
  );
}
