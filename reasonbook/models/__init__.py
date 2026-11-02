# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""SQLAlchemy ORM models."""

from reasonbook.models.agencies import AgencyCatalog
from reasonbook.models.agency_scope import Agency, UserAgencyScope
from reasonbook.models.alerts import Alert, AlertDisposition
from reasonbook.models.auth_tokens import AuthToken
from reasonbook.models.authority import UserSupervisor, UserWorkflowAuthority
from reasonbook.models.connectors import Connector, ConnectorRun
from reasonbook.models.control_points import ControlPoint
from reasonbook.models.decision_types import DecisionType
from reasonbook.models.decisions import Decision, DecisionAttachment, DecisionEvent
from reasonbook.models.disputes import Dispute
from reasonbook.models.ledger import DeterminationLedger
from reasonbook.models.matters import Matter, MatterNode, ParticipantOrg
from reasonbook.models.overrides import AgencySemanticOverride
from reasonbook.models.oversight import (
    OversightCycle,
    OversightEvidenceLink,
    OversightFinding,
)
from reasonbook.models.pipe import PipeRegulatoryCompliance
from reasonbook.models.rfr import RequestForResponse
from reasonbook.models.tenant_lifecycle import TenantLifecycleEvent
from reasonbook.models.tenants import Tenant
from reasonbook.models.users import User, UserAudit

__all__ = [
    "Agency",
    "AgencyCatalog",
    "AgencySemanticOverride",
    "Alert",
    "AlertDisposition",
    "AuthToken",
    "Connector",
    "ConnectorRun",
    "ControlPoint",
    "Decision",
    "DecisionAttachment",
    "DecisionEvent",
    "DecisionType",
    "DeterminationLedger",
    "Dispute",
    "Matter",
    "MatterNode",
    "OversightCycle",
    "OversightEvidenceLink",
    "OversightFinding",
    "ParticipantOrg",
    "PipeRegulatoryCompliance",
    "RequestForResponse",
    "Tenant",
    "TenantLifecycleEvent",
    "User",
    "UserAgencyScope",
    "UserAudit",
    "UserSupervisor",
    "UserWorkflowAuthority",
]

# Register the SEC-1 hash-chain hook on DecisionEvent at model-import time so
# every caller (Flask app, tests, Alembic env, scripts) gets it without an
# explicit registration call. Deferred to the bottom so DecisionEvent is in
# this module's namespace when integrity.hooks resolves it.
from reasonbook.integrity.hooks import register_hash_chain_hook  # noqa: E402

register_hash_chain_hook()
