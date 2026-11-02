// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { useQuery } from "@tanstack/react-query";
import {
  Outlet,
  createRootRoute,
  redirect,
  useLocation,
  useNavigate,
} from "@tanstack/react-router";
import { useEffect } from "react";

import { ApiError } from "@/api/client";
import { type CurrentUser, getMe } from "@/api/auth";
import { NotFoundPage } from "@/components/NotFoundPage";
import { useAuthStore } from "@/stores/auth";

const PUBLIC_PATHS = new Set([
  "/login",
  "/forgot-password",
  "/reset-password",
  "/verify-email",
]);

export const rootRoute = createRootRoute({
  beforeLoad: ({ location }) => {
    // The actual auth guard runs in the component below — this is just to keep
    // the rootRoute typed as having a loader, in case we add SSR-y behaviour
    // later. For pure client routing the component-level guard is enough.
    void location;
  },
  component: RootLayout,
  // 404 page renders OUTSIDE the AppShell wrap below — stale deep-links
  // (e.g. a legacy URL renamed in the rebrand) used
  // to render the rail + topbar with a "Not Found" body inside, which
  // read as "the app is broken" rather than "this URL doesn't exist".
  notFoundComponent: NotFoundPage,
});

function RootLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const status = useAuthStore((s) => s.status);
  const setUser = useAuthStore((s) => s.setUser);

  // Bootstrap auth state on first mount.
  const meQuery = useQuery<CurrentUser, ApiError>({
    queryKey: ["auth", "me"],
    queryFn: getMe,
    enabled: status === "unknown",
    retry: false,
    staleTime: 60_000,
  });

  useEffect(() => {
    if (meQuery.isSuccess) {
      setUser(meQuery.data);
    } else if (meQuery.isError) {
      setUser(null);
    }
  }, [meQuery.isSuccess, meQuery.isError, meQuery.data, setUser]);

  useEffect(() => {
    if (status === "anonymous" && !PUBLIC_PATHS.has(location.pathname)) {
      void navigate({ to: "/login", replace: true });
    }
  }, [status, location.pathname, navigate]);

  if (status === "unknown") {
    return (
      <div className="flex min-h-screen items-center justify-center text-body-sm text-ink-soft">
        Loading…
      </div>
    );
  }

  if (status === "anonymous" && !PUBLIC_PATHS.has(location.pathname)) {
    return null; // Brief blank while we redirect to /login.
  }

  // Every route renders its own shell now (AppShellV2 for authenticated
  // routes, no shell for public routes). Root just renders the Outlet.
  return <Outlet />;
}

// Re-export so route files can keep `() => rootRoute` references.
export { redirect };
