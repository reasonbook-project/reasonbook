// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { createRoute } from "@tanstack/react-router";
import { useState } from "react";

import { ApiError } from "@/api/client";
import type { SettingsUser } from "@/api/settings";
import { SettingsLayout } from "@/components/settings/SettingsLayout";
import { Button } from "@/components/ds/Button";
import { StatusBadge } from "@/components/ds/StatusBadge";
import { HelpLink } from "@/components/help/HelpLink";
import {
  useDeactivateUser,
  useInviteUser,
  useSettingsUsers,
  useUpdateUser,
} from "@/hooks/useSettings";

import { rootRoute } from "../__root";

export const settingsUsersRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/settings/users",
  component: UsersPage,
});

function UsersPage() {
  const usersQuery = useSettingsUsers();
  const [showInvite, setShowInvite] = useState(false);
  const [tempPassword, setTempPassword] = useState<{
    username: string;
    password: string;
  } | null>(null);

  return (
    <SettingsLayout title="Users">
      {tempPassword && (
        <div className="mb-4 rounded-md border-[0.5px] border-info-dot bg-info-bg px-4 py-3">
          <div className="text-tracked uppercase text-info-text">
            Temp password — show this once
          </div>
          <div className="mt-1 font-mono text-body">
            {tempPassword.username}: {tempPassword.password}
          </div>
        </div>
      )}

      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-body-sm text-ink-soft">
            {usersQuery.data?.items.length ?? 0} users
          </span>
          <HelpLink
            topic="settings/users-invite"
            label="How does invite work?"
          />
        </div>
        <Button onClick={() => setShowInvite(true)}>Invite user</Button>
      </div>

      {showInvite && (
        <InviteForm
          onCreated={(user, password) => {
            setShowInvite(false);
            setTempPassword({ username: user.username, password });
          }}
          onCancel={() => setShowInvite(false)}
        />
      )}

      {usersQuery.isLoading && (
        <p className="text-body-sm text-ink-muted">Loading…</p>
      )}
      {usersQuery.isError && (
        <p className="text-body-sm text-critical-text">
          Couldn't load users. Try refreshing.
        </p>
      )}
      {usersQuery.isSuccess && (
        <table className="w-full text-body-sm">
          <thead>
            <tr className="text-tracked uppercase text-ink-soft">
              <th className="py-2 text-left">Name</th>
              <th className="py-2 text-left">Username</th>
              <th className="py-2 text-left">Role</th>
              <th className="py-2 text-left">Status</th>
              <th className="py-2 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {usersQuery.data.items.map((u) => (
              <UserRow key={u.id} user={u} />
            ))}
          </tbody>
        </table>
      )}
    </SettingsLayout>
  );
}

function UserRow({ user }: { user: SettingsUser }) {
  const updateUser = useUpdateUser();
  const deactivateUser = useDeactivateUser();
  const [deactivateError, setDeactivateError] = useState<
    null | { kind: "other"; message: string }
  >(null);

  async function handleDeactivate() {
    setDeactivateError(null);
    try {
      await deactivateUser.mutateAsync(user.id);
    } catch (err) {
      setDeactivateError({
        kind: "other",
        message:
          err instanceof ApiError
            ? `Deactivation failed (HTTP ${err.status})`
            : "Deactivation failed. Try again.",
      });
    }
  }

  return (
    <>
      <tr className="border-t-[0.5px] border-rule-soft">
        <td className="py-3">
          <div>{user.name}</div>
        </td>
        <td className="py-3 font-mono text-[12px] text-ink-soft">
          {user.username}
        </td>
        <td className="py-3">
          <select
            value={user.role}
            onChange={(e) =>
              updateUser.mutate({
                userId: user.id,
                body: { role: e.target.value as "admin" | "member" },
              })
            }
            disabled={updateUser.isPending}
            className="rounded-md border-[0.5px] border-rule-soft bg-paper px-2 py-1 text-body-sm"
          >
            <option value="member">member</option>
            <option value="admin">admin</option>
          </select>
        </td>
        <td className="py-3">
          <StatusBadge
            variant={
              user.status === "active"
                ? "info"
                : user.status === "pending_invite"
                  ? "warning"
                  : "deferred"
            }
            label={user.status}
          />
        </td>
        <td className="py-3 text-right">
          {user.status === "active" && (
            <button
              type="button"
              onClick={handleDeactivate}
              disabled={deactivateUser.isPending}
              className="text-body-sm text-ink-muted hover:text-critical-text"
            >
              Deactivate
            </button>
          )}
        </td>
      </tr>
      {deactivateError && (
        <tr>
          <td colSpan={5} className="border-t-[0.5px] border-rule-soft bg-critical-bg px-3 py-2">
            <div className="text-[13px] text-critical-text">
              {deactivateError.message}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

function InviteForm({
  onCreated,
  onCancel,
}: {
  onCreated: (
    user: { username: string },
    tempPassword: string,
  ) => void;
  onCancel: () => void;
}) {
  const invite = useInviteUser();
  const [name, setName] = useState("");
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<"admin" | "member">("member");

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    invite.mutate(
      { username, email, name, role },
      {
        onSuccess: (data) =>
          onCreated({ username: data.username }, data.temp_password),
      },
    );
  };

  return (
    <form
      onSubmit={submit}
      className="mb-5 grid grid-cols-2 gap-3 rounded-md border-[0.5px] border-rule-soft bg-rule-faint p-4"
    >
      <input
        placeholder="Full name"
        value={name}
        onChange={(e) => setName(e.target.value)}
        required
        className="rounded-md border-[0.5px] border-rule-soft bg-paper px-3 py-2 text-body-sm"
      />
      <input
        placeholder="username"
        value={username}
        onChange={(e) => setUsername(e.target.value)}
        required
        className="rounded-md border-[0.5px] border-rule-soft bg-paper px-3 py-2 text-body-sm font-mono"
      />
      <input
        placeholder="email"
        type="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        required
        className="rounded-md border-[0.5px] border-rule-soft bg-paper px-3 py-2 text-body-sm"
      />
      <select
        value={role}
        onChange={(e) => setRole(e.target.value as "admin" | "member")}
        className="rounded-md border-[0.5px] border-rule-soft bg-paper px-3 py-2 text-body-sm"
      >
        <option value="member">member</option>
        <option value="admin">admin</option>
      </select>
      {invite.isError && (
        <p className="col-span-2 text-body-sm text-critical-text">
          Invite failed. Username might already be taken.
        </p>
      )}
      <div className="col-span-2 flex justify-end gap-2">
        <button
          type="button"
          onClick={onCancel}
          className="text-body-sm text-ink-muted"
        >
          Cancel
        </button>
        <Button type="submit" disabled={invite.isPending}>
          {invite.isPending ? "Inviting…" : "Send invite"}
        </Button>
      </div>
    </form>
  );
}
