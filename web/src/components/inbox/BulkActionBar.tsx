// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { useState } from "react";

import { ApiError } from "@/api/client";
import type { BulkResponse } from "@/api/decisions";
import { Button } from "@/components/ds/Button";
import { useBulkClaim, useBulkComment } from "@/hooks/useDecisions";
import { cn } from "@/lib/cn";

/**
 * Sticky banner that appears at the top of the Inbox whenever ≥1
 * decision is selected (Phase 8.5 bulk-ops). Surfaces:
 *
 *   - selection count + "Clear" affordance
 *   - "Claim" — bulk-claims everything in the selection where this
 *     user has authority and the decision isn't already past `in_progress`
 *   - "Comment" — opens an inline composer; posts the same comment
 *     under stage_context='general' on every visible decision
 *
 * Per the amendment §5: every bulk action returns a structured
 * per-decision result list. When a request returns mixed success, we
 * surface both counts inline so the operator sees exactly which
 * decisions weren't touched and why.
 *
 * Defer / Reassign are noted in the action menu but disabled in v1 —
 * Defer needs a date picker and Reassign needs a per-tenant user list
 * endpoint. Both are tracked alongside the v2 upload features in the
 * backlog.
 */
export function BulkActionBar({
  selectedIds,
  onClear,
}: {
  selectedIds: string[];
  onClear: () => void;
}) {
  const claim = useBulkClaim();
  const comment = useBulkComment();
  const [composerOpen, setComposerOpen] = useState(false);
  const [commentBody, setCommentBody] = useState("");
  const [feedback, setFeedback] = useState<{
    kind: "ok" | "warn" | "error";
    text: string;
  } | null>(null);

  const count = selectedIds.length;
  if (count === 0) return null;
  const noun = count === 1 ? "decision" : "decisions";

  const handleResult = (resp: BulkResponse, op: string) => {
    // Don't auto-clear selection — the bar would unmount before the user
    // sees the feedback. The user dismisses with the Clear button when
    // they're done. Re-clicking Claim after a successful claim is fine:
    // the server returns "already in progress" partial-success per id,
    // which surfaces correctly in the warn branch below.
    if (resp.failed === 0) {
      setFeedback({
        kind: "ok",
        text: `${op}: ${resp.succeeded} ${noun}.`,
      });
    } else {
      const firstError =
        resp.results.find((r) => !r.ok)?.error ?? "unknown error";
      setFeedback({
        kind: "warn",
        text: `${op}: ${resp.succeeded} succeeded · ${resp.failed} skipped (e.g. "${firstError}").`,
      });
    }
  };

  const handleError = (err: unknown) => {
    if (err instanceof ApiError) {
      const body = err.body as { error?: string } | null;
      setFeedback({
        kind: "error",
        text: body?.error ?? `Failed (${err.status})`,
      });
    } else {
      setFeedback({ kind: "error", text: "Bulk action failed" });
    }
  };

  return (
    <div
      role="region"
      aria-label="Bulk actions"
      className="sticky top-2 z-10 mb-3 rounded-md border border-navy/30 bg-navy-tint px-4 py-3 shadow-sm"
    >
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-body-sm font-medium text-ink">
          {count} {noun} selected
        </span>
        <button
          type="button"
          onClick={onClear}
          className="text-body-sm text-ink-muted hover:text-ink"
        >
          Clear
        </button>

        <span aria-hidden className="ml-auto text-ink-faint">
          ·
        </span>

        <Button
          compact
          onClick={() => {
            setFeedback(null);
            claim.mutate(selectedIds, {
              onSuccess: (resp) => handleResult(resp, "Claimed"),
              onError: handleError,
            });
          }}
          disabled={claim.isPending}
        >
          {claim.isPending ? "Claiming…" : "Claim"}
        </Button>
        <Button
          compact
          variant="ghost"
          onClick={() => {
            setComposerOpen((v) => !v);
            setFeedback(null);
          }}
        >
          {composerOpen ? "Cancel comment" : "Comment"}
        </Button>
      </div>

      {composerOpen && (
        <form
          className="mt-3 space-y-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (!commentBody.trim()) return;
            setFeedback(null);
            comment.mutate(
              { ids: selectedIds, body: commentBody.trim() },
              {
                onSuccess: (resp) => {
                  setComposerOpen(false);
                  setCommentBody("");
                  handleResult(resp, "Commented");
                },
                onError: handleError,
              },
            );
          }}
        >
          <textarea
            value={commentBody}
            onChange={(e) => setCommentBody(e.target.value)}
            rows={2}
            placeholder={`Comment to post on ${count} ${noun}…`}
            className="w-full resize-y rounded-md border border-rule bg-paper px-3 py-2 text-body-sm focus:border-navy focus:outline-none focus:ring-2 focus:ring-navy-soft"
          />
          <div className="flex justify-end">
            <Button
              compact
              type="submit"
              disabled={!commentBody.trim() || comment.isPending}
            >
              {comment.isPending ? "Posting…" : `Post on ${count} ${noun}`}
            </Button>
          </div>
        </form>
      )}

      {feedback && (
        <div
          role="status"
          className={cn(
            "mt-2 text-body-sm",
            feedback.kind === "ok" && "text-resolved-text",
            feedback.kind === "warn" && "text-warning-text",
            feedback.kind === "error" && "text-critical-text",
          )}
        >
          {feedback.text}
        </div>
      )}
    </div>
  );
}
