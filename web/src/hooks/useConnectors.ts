// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  listConnectorRuns,
  listConnectors,
  syncConnector,
} from "@/api/connectors";

const CONNECTORS_KEY = "connectors" as const;

export function useConnectors() {
  return useQuery({
    queryKey: [CONNECTORS_KEY, "list"],
    queryFn: listConnectors,
    staleTime: 30_000,
  });
}

export function useConnectorRuns(
  connectorId: string | undefined,
  { enabled = true }: { enabled?: boolean } = {},
) {
  return useQuery({
    queryKey: [CONNECTORS_KEY, "runs", connectorId],
    queryFn: () => listConnectorRuns(connectorId as string),
    enabled: enabled && Boolean(connectorId),
    staleTime: 5_000,
  });
}

export function useSyncConnector() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (connectorId: string) => syncConnector(connectorId),
    onSuccess: (_data, connectorId) => {
      void qc.invalidateQueries({ queryKey: [CONNECTORS_KEY, "list"] });
      void qc.invalidateQueries({
        queryKey: [CONNECTORS_KEY, "runs", connectorId],
      });
    },
  });
}
