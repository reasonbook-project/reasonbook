// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

/**
 * Admin API client — internal-only provisioning tools.
 *
 * Per spec-2 Component 5.5 (Enterprise admin provisioning) and forward
 * to Component 5.6 (Implementation Services). Backend gates these
 * endpoints with ``@require_admin``; frontend hides the routes from
 * non-admins via the role check on ``useAuthStore``.
 */

import { apiFetch } from "./client";

export type ProvisionMode = "existing" | "new";
export type BillingInterval = "monthly" | "annual";
export type CollectionMethod = "send_invoice" | "charge_automatically";

export type ProvisionEnterprisePayload = {
  mode: ProvisionMode;
  interval: BillingInterval;
  collection_method: CollectionMethod;
  po_number?: string;
  notes?: string;

  // mode === "existing"
  email?: string;

  // mode === "new"
  tenant_name?: string;
  admin_email?: string;
  admin_name?: string;
};

export type ProvisionEnterpriseResponse = {
  tenant_id: string;
  subscription_id: string;
  status: string; // 'incomplete' | 'active' | etc.
  hosted_invoice_url: string | null;
  admin_email: string;
  password_reset_sent: boolean;
  interval: BillingInterval;
  collection_method: CollectionMethod;
};

export function provisionEnterprise(
  payload: ProvisionEnterprisePayload,
): Promise<ProvisionEnterpriseResponse> {
  return apiFetch<ProvisionEnterpriseResponse>(
    "/api/admin/provision-enterprise",
    {
      method: "POST",
      body: payload,
    },
  );
}

export type SellServicesPayload = {
  email: string;
  blocks: number;
  po_number?: string;
  notes?: string;
  send_now: boolean;
};

export type SellServicesResponse = {
  tenant_id: string;
  invoice_id: string;
  hosted_invoice_url: string | null;
  amount_cents: number;
  blocks: number;
  status: "draft" | "sent";
  stripe_status: string;
  admin_email: string;
};

export function sellServices(
  payload: SellServicesPayload,
): Promise<SellServicesResponse> {
  return apiFetch<SellServicesResponse>("/api/admin/sell-services", {
    method: "POST",
    body: payload,
  });
}
