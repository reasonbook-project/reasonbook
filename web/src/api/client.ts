// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

/**
 * Thin fetch wrapper.
 *
 * Always sends cookies (`credentials: 'include'`) so the HTTP-only session
 * cookie set by the backend on `/api/auth/login` is included on every
 * subsequent call.
 *
 * In dev, all requests go to the same origin (localhost:5173) and are proxied
 * through Vite to the Flask API at localhost:5001 — see vite.config.ts.
 */

export class ApiError extends Error {
  status: number;
  body: unknown;

  constructor(status: number, body: unknown, message?: string) {
    super(message ?? `API error ${status}`);
    this.status = status;
    this.body = body;
  }
}

type RequestOptions = Omit<RequestInit, "body"> & {
  body?: unknown;
};

export async function apiFetch<T>(
  path: string,
  { body, headers, ...rest }: RequestOptions = {},
): Promise<T> {
  const init: RequestInit = {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
      ...(headers ?? {}),
    },
    ...rest,
  };
  if (body !== undefined) {
    init.body = JSON.stringify(body);
  }

  const resp = await fetch(path, init);
  const text = await resp.text();
  const parsed: unknown = text ? safeJson(text) : null;

  if (!resp.ok) {
    throw new ApiError(resp.status, parsed);
  }
  return parsed as T;
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}
