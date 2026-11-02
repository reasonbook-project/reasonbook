// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { ApiError } from "@/api/client";
import type { Decision } from "@/api/decisions";
import type { WorkflowAction } from "@/api/workflows";
import { Button } from "@/components/ds/Button";
import { useFinalizeDecision } from "@/hooks/useDecisions";
import { cn } from "@/lib/cn";

const schema = z.object({
  selected_option: z.string().min(1, "Pick an option"),
  rationale: z.string().min(20, "Rationale must be at least 20 characters"),
});
type FormValues = z.infer<typeof schema>;

/**
 * Finalize form — appears in stage 3 (Decision) when status is in_progress.
 *
 * Options render as a 2-column tile grid per the composite mockup; the
 * first tile is treated as the "recommended" default (workflow YAML
 * doesn't carry a recommended flag today — see the retire-standalone
 * backlog for the follow-up that lets configs annotate this). Rationale
 * is a full textarea; Record decision is the primary CTA.
 */
export function FinalizeForm({
  decision,
  availableActions,
}: {
  decision: Decision;
  availableActions: WorkflowAction[];
}) {
  const finalize = useFinalizeDecision();
  const {
    register,
    handleSubmit,
    watch,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { selected_option: "", rationale: "" },
  });

  const selected = watch("selected_option");

  const onSubmit = (values: FormValues) => {
    finalize.mutate({
      decisionId: decision.id,
      body: {
        selected_option: values.selected_option,
        rationale: values.rationale,
      },
    });
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} noValidate className="space-y-4">
      <div>
        {availableActions.length === 0 ? (
          <p className="text-body-sm text-ink-muted">
            No available actions defined for this decision type.
          </p>
        ) : (
          <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
            {availableActions.map((action, idx) => {
              const isSelected = selected === action.id;
              // Convention: first action = recommended default. Workflow
              // configs don't carry an explicit recommended flag today.
              const isRecommended = idx === 0;
              return (
                <label
                  key={action.id}
                  className={cn(
                    "relative flex cursor-pointer flex-col rounded-md border-[0.5px] px-3.5 py-3 transition-colors",
                    isSelected
                      ? "border-navy border-[1.5px] bg-navy-soft"
                      : isRecommended
                        ? "border-navy bg-navy-soft/60 hover:bg-navy-soft"
                        : "border-rule-soft bg-paper hover:border-rule",
                  )}
                >
                  <input
                    type="radio"
                    value={action.id}
                    {...register("selected_option")}
                    className="sr-only"
                  />
                  <span className="flex items-baseline gap-2">
                    <span
                      className={cn(
                        "text-body font-medium",
                        isSelected || isRecommended
                          ? "text-navy-deep"
                          : "text-ink",
                      )}
                    >
                      {action.name}
                    </span>
                    {isRecommended && !isSelected && (
                      <span className="inline-block rounded-sm bg-paper px-1.5 py-[1px] text-[9px] font-medium uppercase tracking-[0.08em] text-navy-deep">
                        Recommended
                      </span>
                    )}
                  </span>
                  {action.description && (
                    <span className="mt-1 text-body-sm text-ink-soft">
                      {action.description}
                    </span>
                  )}
                  <span className="mt-1.5 font-mono text-[10px] uppercase tracking-[0.06em] text-ink-faint">
                    authority · {action.authority_required} · impact ·{" "}
                    {action.impact}
                  </span>
                </label>
              );
            })}
          </div>
        )}
        {errors.selected_option && (
          <p className="mt-1 text-[11px] text-critical-text">
            {errors.selected_option.message}
          </p>
        )}
      </div>

      <div>
        <label
          htmlFor="rationale"
          className="text-tracked uppercase text-ink-soft"
        >
          Rationale — brief note on the record (required)
        </label>
        <textarea
          id="rationale"
          rows={3}
          className="mt-2 w-full rounded-md border-[0.5px] border-rule bg-paper px-3 py-2 text-body leading-[1.55] text-ink placeholder:text-ink-faint focus:border-navy focus:outline-none focus:ring-2 focus:ring-navy-soft"
          placeholder="Why this option, what backs it, what alternatives were considered."
          {...register("rationale")}
        />
        {errors.rationale && (
          <p className="mt-1 text-[11px] text-critical-text">
            {errors.rationale.message}
          </p>
        )}
      </div>

      {finalize.isError && finalize.error instanceof ApiError && (
        <p className="text-body-sm text-critical-text">
          {finalize.error.status === 403
            ? "You don't have authority to take this action."
            : ((finalize.error.body as { error?: string })?.error ??
              "Finalize failed.")}
        </p>
      )}

      <div className="flex items-center justify-end gap-2">
        <Button type="button" variant="ghost">
          Escalate
        </Button>
        <Button type="button" variant="ghost">
          Hold
        </Button>
        <Button type="submit" disabled={finalize.isPending}>
          {finalize.isPending ? "Recording…" : "Record decision →"}
        </Button>
      </div>
    </form>
  );
}
