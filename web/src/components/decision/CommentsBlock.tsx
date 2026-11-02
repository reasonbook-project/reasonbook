// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { format, parseISO } from "date-fns";
import { useState } from "react";

import type { DecisionEvent, StageContext } from "@/api/decisions";
import { ApiError } from "@/api/client";
import { Button } from "@/components/ds/Button";
import { HelpLink } from "@/components/help/HelpLink";
import {
  useCreateComment,
  useDecisionEvents,
} from "@/hooks/useDecisions";
import { useAuthStore } from "@/stores/auth";

/**
 * Comment thread scoped to one stage_context. Per Phase 7.5 Gate 7, comments
 * are events with action='comment' on decision_events; this component reads
 * include=comments and posts under the given stage_context.
 *
 * v1 ships plain text — no @mention autocomplete (deferred until a
 * tenant-users endpoint exists). Author display reads `user_name` off the
 * event payload (the events API bulk-joins User by user_id); falls back to
 * a generic label only when the event has no user_id.
 */
export function CommentsBlock({
  decisionId,
  stageContext,
  label,
}: {
  decisionId: string;
  stageContext: StageContext;
  label?: string;
}) {
  const me = useAuthStore((s) => s.user);
  const eventsQuery = useDecisionEvents(decisionId, "comments");
  const create = useCreateComment();

  const [body, setBody] = useState("");
  const [error, setError] = useState<string | null>(null);

  const comments = (eventsQuery.data?.items ?? [])
    .filter((e) => {
      const ctx =
        (e.metadata as { stage_context?: string } | null)?.stage_context ??
        "general";
      return ctx === stageContext;
    })
    .sort((a, b) => a.created_at.localeCompare(b.created_at));

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!body.trim()) return;
    setError(null);
    create.mutate(
      {
        decisionId,
        body: { body: body.trim(), stage_context: stageContext },
      },
      {
        onSuccess: () => setBody(""),
        onError: (err) => {
          if (err instanceof ApiError) {
            const errBody = err.body as { error?: string } | null;
            setError(errBody?.error ?? `Failed (${err.status})`);
          } else {
            setError("Failed to post comment");
          }
        },
      },
    );
  };

  return (
    <div className="mt-4">
      <div className="flex items-center gap-2">
        <div className="text-tracked uppercase text-ink-soft">
          {label ?? "Comments"}
        </div>
        <HelpLink
          topic="decisions/comment"
          variant="icon"
          ariaLabel="Help: commenting on a decision"
        />
      </div>

      {comments.length > 0 && (
        <ul className="mt-2 space-y-2">
          {comments.map((c) => (
            <Comment key={c.id} event={c} currentUserId={me?.id} currentUserName={me?.name} />
          ))}
        </ul>
      )}

      <form onSubmit={handleSubmit} className="mt-2 space-y-2">
        <textarea
          value={body}
          onChange={(e) => setBody(e.target.value)}
          rows={2}
          placeholder={
            comments.length === 0
              ? "Add a comment to this stage…"
              : "Reply…"
          }
          className="w-full resize-y rounded-md border border-rule bg-paper px-3 py-2 text-body-sm leading-relaxed focus:border-navy focus:outline-none focus:ring-2 focus:ring-navy-soft"
        />
        {error && (
          <div role="alert" className="text-body-sm text-critical-text">
            {error}
          </div>
        )}
        <div className="flex justify-end">
          <Button
            type="submit"
            compact
            disabled={!body.trim() || create.isPending}
          >
            {create.isPending ? "Posting…" : "Post comment"}
          </Button>
        </div>
      </form>
    </div>
  );
}

function Comment({
  event,
  currentUserId,
  currentUserName,
}: {
  event: DecisionEvent;
  currentUserId?: string;
  currentUserName?: string;
}) {
  const isSelf = event.user_id && currentUserId && event.user_id === currentUserId;
  const author = isSelf
    ? (currentUserName ?? event.user_name ?? "You")
    : (event.user_name ?? "Unknown user");
  const when = format(parseISO(event.created_at), "MMM d, h:mm a");

  return (
    <li className="rounded-md border-[0.5px] border-rule-soft bg-navy-tint/40 px-3 py-2">
      <div className="flex items-baseline gap-2 text-body-sm">
        <span className="font-medium text-ink">{author}</span>
        <span className="font-mono text-[11px] text-ink-faint">
          {when}
        </span>
      </div>
      {event.comment && (
        <p className="mt-1 text-body-sm leading-[1.55] text-ink whitespace-pre-wrap">
          {event.comment}
        </p>
      )}
    </li>
  );
}
