"""Dispatch for the canonical state-changing auth endpoints.

Every endpoint is operation-specific: it attempts exactly the operation the inventory names
for its route and method. Challenge-bearing endpoints run the shared prepare and completion
procedures first and apply their own proof and mutation rules only after; the three
operations outside that subset apply their endpoint rules directly, with no challenge
mechanics anywhere on their path.
"""

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from nativespeaker.api.auth.modes import RequestMode, classify_mode
from nativespeaker.api.auth.operations import (
    CHALLENGE_BEARING_OPERATIONS,
    AuthOperation,
    IdentityProvider,
    is_challenge_bearing,
    normalize_variant,
)

PROVIDER_FIELD = "provider"


class OperationMismatchError(RuntimeError):
    """A request was about to be handled as an operation other than the one its route names."""


class ChallengeScopeError(RuntimeError):
    """Challenge machinery was reached for an operation outside the challenge-bearing subset."""


class EndpointRules(Protocol):
    """The endpoint-specific half: proof, live-state and mutation rules for one operation."""
    operation: AuthOperation

    async def run(self, identity: Any, body: Mapping[str, Any] | None) -> Any:
        ...


class SharedChallengeProcedures(Protocol):
    """The shared prepare and completion procedures every challenge-bearing endpoint uses."""

    async def prepare(self,
                      operation: AuthOperation,
                      variant: IdentityProvider | None,
                      identity: Any,
                      endpoint: Any,
                      *,
                      attempt: Any = None,
                      body: Mapping[str, Any] | None = None) -> Any:
        ...

    async def complete(self,
                       operation: AuthOperation,
                       declared_variant: str | None,
                       challenge_id: str,
                       identity: Any,
                       endpoint: Any,
                       *,
                       attempt: Any = None,
                       body: Mapping[str, Any] | None = None) -> Any:
        ...


async def dispatch_state_changing(*,
                                  operation: AuthOperation,
                                  endpoint: EndpointRules,
                                  identity: Any,
                                  query_items: Sequence[tuple[str, str]],
                                  body: Mapping[str, Any] | None,
                                  shared: SharedChallengeProcedures,
                                  attempt: Any = None) -> Any:
    """Run one attempt at the operation the inventory names for this route."""
    # The backend never reinterprets a request as another operation and never silently falls
    # through to a different mutation.
    # [impl->req~shared-endpoint-operation-specific~1]
    if endpoint.operation is not operation:
        raise OperationMismatchError(
            f"{endpoint.operation} cannot serve a request routed to {operation}")

    if not is_challenge_bearing(operation):
        # Outside the challenge-bearing subset nothing issues, presents, validates or consumes
        # a challenge: the endpoint rules apply directly, under the shared barrier, audit and
        # admission obligations that bind the whole inventory. No such endpoint has a prepare
        # mode, so `challenge=true` on one of them is not a recognized signal.
        # [impl->req~shared-challenge-scope-narrower-subset~1]
        # [impl->req~shared-flow-order-shared-then-specific~1]
        # [impl->req~shared-prepare-mode-signal~1]
        return await endpoint.run(identity, body)

    # The syntactic mode-signal partition runs after the shared barrier's checks and before any
    # challenge processing, so a request carrying both signals or neither is rejected as
    # `invalid_request` without issuing or consuming a challenge.
    # [impl->req~shared-completion-mode-signal-invalid~1]
    signal = classify_mode(query_items, body)
    # The completion body carries the same `challenge_id` verbatim and, where the operation
    # defines a variant, the `provider` field holding the same normalized declaration.
    # [impl->req~shared-wire-completion-body~1]
    declared = body.get(PROVIDER_FIELD) if body else None

    # Shared procedures first; the endpoint's own rules run inside them, never ahead of them.
    # [impl->req~shared-endpoints-use-shared-procedures~1]
    # [impl->req~shared-flow-order-shared-then-specific~1]
    # [impl->req~shared-internal-reuse-allowed~1]
    if signal.mode is RequestMode.prepare:
        # Prepare mode is requested by `challenge=true` on the endpoint's own URL.
        # [impl->req~shared-prepare-mode-signal~1]
        # Normalization happens only at prepare; the challenge binds the normalized variant.
        variant = normalize_variant(operation, None if declared is None else str(declared))
        return await shared.prepare(operation, variant, identity, endpoint,
                                    attempt=attempt, body=body)
    assert signal.challenge_id is not None
    # Completion applies the declaration it received, compared exactly against the stored one.
    return await shared.complete(operation, declared, signal.challenge_id, identity, endpoint,
                                 attempt=attempt, body=body)


def assert_challenge_bearing(operation: AuthOperation) -> None:
    """Guard for the challenge store: only the narrower subset may reach it."""
    # [impl->req~shared-challenge-scope-narrower-subset~1]
    if operation not in CHALLENGE_BEARING_OPERATIONS:
        raise ChallengeScopeError(f"{operation} has no challenge mechanics")
