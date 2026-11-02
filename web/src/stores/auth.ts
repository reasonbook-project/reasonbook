// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { create } from "zustand";

import type { CurrentUser } from "@/api/auth";

type AuthStatus = "unknown" | "authenticated" | "anonymous";

type AuthState = {
  status: AuthStatus;
  user: CurrentUser | null;
  setUser: (user: CurrentUser | null) => void;
  setStatus: (status: AuthStatus) => void;
  reset: () => void;
};

export const useAuthStore = create<AuthState>((set) => ({
  status: "unknown",
  user: null,
  setUser: (user) =>
    set({ user, status: user ? "authenticated" : "anonymous" }),
  setStatus: (status) => set({ status }),
  reset: () => set({ user: null, status: "anonymous" }),
}));
