// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { format, parseISO } from "date-fns";
import { useRef, useState } from "react";

import { ApiError } from "@/api/client";
import { attachmentDownloadUrl, type AttachmentStage } from "@/api/decisions";
import { HelpLink } from "@/components/help/HelpLink";
import {
  useDecisionAttachments,
  useDeleteAttachment,
  useUploadAttachment,
} from "@/hooks/useDecisions";
import { cn } from "@/lib/cn";

/**
 * Attachments scoped to one anatomy stage. Lists active uploads, lets
 * authorized users add files (multipart) and soft-delete them. Soft-delete
 * sets superseded_at on the row; the bytes drop too.
 *
 * Authority is enforced server-side; the UI surfaces 403s as inline errors
 * rather than gating the affordance.
 */
export function AttachmentsBlock({
  decisionId,
  stage,
  label,
}: {
  decisionId: string;
  stage: AttachmentStage;
  /** Optional override for the section label. Defaults to "Attachments". */
  label?: string;
}) {
  const query = useDecisionAttachments(decisionId);
  const upload = useUploadAttachment();
  const remove = useDeleteAttachment();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);

  const attachments = (query.data?.items ?? [])
    .filter((a) => a.stage === stage && a.superseded_at === null)
    .sort((a, b) => (b.uploaded_at ?? "").localeCompare(a.uploaded_at ?? ""));

  const handleFiles = (files: FileList | File[]) => {
    setError(null);
    const arr = Array.from(files);
    for (const file of arr) {
      upload.mutate(
        { decisionId, file, stage },
        {
          onError: (err) => {
            if (err instanceof ApiError) {
              const body = err.body as { error?: string } | null;
              setError(body?.error ?? `Upload failed (${err.status})`);
            } else {
              setError(`Upload failed: ${file.name}`);
            }
          },
        },
      );
    }
  };

  const handleDelete = (attachmentId: string) => {
    setError(null);
    remove.mutate(
      { decisionId, attachmentId },
      {
        onError: (err) => {
          if (err instanceof ApiError) {
            const body = err.body as { error?: string } | null;
            setError(body?.error ?? `Delete failed (${err.status})`);
          } else {
            setError("Delete failed");
          }
        },
      },
    );
  };

  return (
    <div className="mt-4">
      <div className="flex items-center gap-2">
        <div className="text-tracked uppercase text-ink-soft">
          {label ?? "Attachments"}
        </div>
        <HelpLink
          topic="decisions/attach-evidence"
          variant="icon"
          ariaLabel="Help: attaching evidence"
        />
      </div>

      {attachments.length > 0 && (
        <ul className="mt-2 divide-y divide-rule-soft border-[0.5px] border-rule-soft rounded-md bg-paper">
          {attachments.map((att) => (
            <li
              key={att.id}
              className="flex items-center gap-3 px-3 py-2 text-body-sm"
            >
              <a
                href={attachmentDownloadUrl(decisionId, att.id)}
                target="_blank"
                rel="noopener noreferrer"
                className="min-w-0 flex-1 truncate text-ink hover:text-navy"
                title={att.filename}
              >
                {att.filename}
              </a>
              <span className="font-mono text-[11px] text-ink-faint">
                {formatBytes(att.size_bytes)}
              </span>
              {att.uploaded_at && (
                <span className="hidden text-ink-faint md:inline">
                  {format(parseISO(att.uploaded_at), "MMM d")}
                </span>
              )}
              <button
                type="button"
                onClick={() => handleDelete(att.id)}
                disabled={remove.isPending}
                aria-label={`Remove ${att.filename}`}
                className="text-ink-faint hover:text-critical-text disabled:opacity-50"
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}

      <div
        className={cn(
          "mt-2 flex items-center justify-between gap-3 rounded-md border border-dashed px-3 py-2 transition-colors",
          dragOver ? "border-navy bg-navy-tint" : "border-rule",
        )}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          if (e.dataTransfer.files.length > 0) handleFiles(e.dataTransfer.files);
        }}
      >
        <span className="text-body-sm text-ink-muted">
          {attachments.length === 0
            ? "No files yet."
            : `${attachments.length} file${attachments.length === 1 ? "" : "s"}.`}
          {" "}Drop here or
        </span>
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={upload.isPending}
          className="text-body-sm font-medium text-navy hover:text-navy-deep disabled:opacity-50"
        >
          {upload.isPending ? "Uploading…" : "choose files"}
        </button>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          className="hidden"
          onChange={(e) => {
            if (e.target.files && e.target.files.length > 0) {
              handleFiles(e.target.files);
              e.target.value = "";
            }
          }}
        />
      </div>

      {error && (
        <div role="alert" className="mt-2 text-body-sm text-critical-text">
          {error}
        </div>
      )}
    </div>
  );
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}
