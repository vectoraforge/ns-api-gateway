"""What the three challenge-free authenticated endpoints share before their own logic runs.

`POST /auth/sync`, `GET /users/me` and `POST /auth/sign-out-all` each state the same two
preconditions: the external IDP ID token arrives as a single `Authorization: Bearer` credential,
and authentication plus identity resolution already happened in the shared pre-handler barrier,
which admits only a linked, active identity. Both are decided here, once, against the route
registries that already own the underlying rules — the wire contract in `barrier` and the route
policy in `routes` — so an endpoint cannot quietly accept a second credential location or a
non-linked outcome by forgetting a check.
"""

from collections.abc import Sequence

from nativespeaker.api.auth.audit import AuthEventResult
from nativespeaker.api.auth.barrier import (
    BarrierRejectionError,
    ResolutionOutcome,
    VerifiedIdentityContext,
    barrier_result_for,
    extract_bearer_token,
)
from nativespeaker.api.auth.routes import (
    ID_TOKEN_REQUIRED_ROUTES,
    RouteCategory,
    categorize,
)


class EndpointContractError(RuntimeError):
    """An endpoint was about to authenticate outside the shared wire and barrier contract."""


def bearer_credential(method: str, path: str, authorization_values: Sequence[str]) -> str:
    """The endpoint's whole authentication input: the external IDP ID token, presented as exactly
    one `Authorization: Bearer` credential.

    The route has to be one that declares the ID token required, and the credential is taken by
    the barrier's single-carrier extractor — so a missing, duplicated, comma-folded, multi-valued
    or non-`Bearer` `Authorization` field is rejected for this endpoint exactly as for every
    other, and no query parameter, cookie, body field or `X-*` header can stand in for it.
    """
    route = (method.upper(), path)
    if route not in ID_TOKEN_REQUIRED_ROUTES:
        raise EndpointContractError(f"{method} {path} declares no ID token requirement")
    return extract_bearer_token(authorization_values)


def barrier_admitted(context: VerifiedIdentityContext,
                     method: str,
                     path: str) -> VerifiedIdentityContext:
    """The endpoint's admission precondition: it consumes the barrier's typed output and requires
    a linked, active identity.

    Authentication and identity resolution happen in the shared pre-handler barrier before the
    handler runs, so pre-auth, historical and blocked identities never reach it — this reads the
    barrier's own policy predicate rather than restating which outcomes are rejected, and raises
    the barrier's rejection for any outcome that predicate refuses. A linked outcome carrying no
    resolved user is refused too: it is not an admitted principal either.
    """
    if categorize(method, path) is not RouteCategory.authenticated:
        raise EndpointContractError(f"{method} {path} is not an authenticated route")
    result = barrier_result_for(context.outcome, method.upper(), path)
    if result is not None:
        raise BarrierRejectionError(result)
    if context.outcome is not ResolutionOutcome.linked or context.user_id is None:
        raise BarrierRejectionError(AuthEventResult.invalid_external_jwt)
    return context
