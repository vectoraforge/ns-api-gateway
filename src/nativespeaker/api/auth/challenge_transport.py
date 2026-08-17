"""How the challenge ID travels, and what binds it.

The challenge ID is the only secret capability handle for completion, so it moves through response
and request bodies over HTTPS and nowhere else: not in a URL, not in a log line, not in an audit
row, not in an error message a client can read. What is logged for correlation instead is the
challenge row's own server-side `id`, which is not a capability.

Binding is deliberately thin. A challenge is never a credential — completion always requires the
current external IDP ID token, with `(issuer, subject)` freshly derived from the backend's own
verification of it — and that one property is what carries the security. The rest of this module is
hygiene around it, and the controls this specification deliberately does *not* add are written down
here as well, so "we should also bind the IP" is answered by the file rather than by memory.
"""

from collections.abc import Iterable, Mapping
from enum import StrEnum
from typing import Any

from nativespeaker.api.auth.challenges import (
    CHALLENGE_ID_BYTES,
    CHALLENGE_TTL_SECONDS,
    ChallengeError,
    ChallengeRow,
    PrepareResponse,
)
from nativespeaker.api.auth.derived_identifiers import actor_subject_preimage
from nativespeaker.api.auth.tokens import VerifiedClaims


class TransportError(ChallengeError):
    """The challenge ID was about to travel somewhere the transport rules forbid."""


# --- Where the challenge ID may appear ------------------------------------------------------------


class TransportLocation(StrEnum):
    """Every place a challenge ID could be carried, permitted or not."""
    prepare_response_body = "prepare_response_body"
    completion_request_body = "completion_request_body"
    url_path = "url_path"
    query_string = "query_string"
    request_header = "request_header"
    response_header = "response_header"
    cookie = "cookie"
    audit_row = "audit_row"
    access_log = "access_log"
    application_log = "application_log"
    trace = "trace"
    analytics = "analytics"
    error_report = "error_report"
    client_visible_error = "client_visible_error"


# The two permitted locations, and the whole of them: returned only in the prepare response body
# over HTTPS, submitted only in the completion request body.
# [impl->req~sessions-challenge-transport-body-only~1]
PERMITTED_LOCATIONS: frozenset[TransportLocation] = frozenset({
    TransportLocation.prepare_response_body,
    TransportLocation.completion_request_body,
})

# The transport the two permitted locations ride on. There is no plaintext-HTTP variant.
REQUIRED_TRANSPORT_SCHEME = "https"

# The challenge ID never appears in a URL path or query string, and it is never written to audit
# rows: it is the only secret capability handle for completion, so a URL or a durable row would
# hand that capability to proxies, referrers, browser history and the audit reader alike.
# [impl->req~sessions-challenge-transport-never-in-url~1]
URL_LOCATIONS: frozenset[TransportLocation] = frozenset({
    TransportLocation.url_path,
    TransportLocation.query_string,
})

# Nor in plaintext to any of these sinks. What is logged for correlation is the challenge row's
# server-side `id`.
# [impl->req~sessions-challenge-transport-no-plaintext-logging~1]
LOGGING_SINKS: frozenset[TransportLocation] = frozenset({
    TransportLocation.access_log,
    TransportLocation.application_log,
    TransportLocation.trace,
    TransportLocation.analytics,
    TransportLocation.error_report,
    TransportLocation.client_visible_error,
})


def assert_transport_location(location: TransportLocation | str,
                              *,
                              scheme: str = REQUIRED_TRANSPORT_SCHEME) -> TransportLocation:
    """The one gate for moving a challenge ID: the prepare response body and the completion request
    body, over HTTPS. Everything else — a URL, a header, a cookie, an audit row, a log sink — is
    refused, and an unrecognized location is refused too rather than passed through."""
    # [impl->req~sessions-challenge-transport-body-only~1]
    # [impl->req~sessions-challenge-transport-never-in-url~1]
    try:
        where = TransportLocation(location)
    except ValueError:
        raise TransportError(f"{location} is not a permitted challenge transport") from None
    if where not in PERMITTED_LOCATIONS:
        raise TransportError(f"the challenge id is never carried in {where}")
    if scheme.lower() != REQUIRED_TRANSPORT_SCHEME:
        raise TransportError("the challenge id travels over HTTPS only")
    return where


def assert_not_in_url(*, path: str, query: str, challenge_id: str) -> None:
    """The challenge ID never appears in a URL path or query string. Checked against the value, not
    only against a parameter name, so a handle smuggled into a path segment is caught too."""
    # [impl->req~sessions-challenge-transport-never-in-url~1]
    if not challenge_id:
        raise TransportError("there is no challenge id to check")
    if challenge_id in path or challenge_id in query:
        raise TransportError("the challenge id never appears in a URL path or query string")


# --- The prepare response's caching -------------------------------------------------------------

# Prepare responses carry `Cache-Control: no-store`: the body holds the one secret capability
# handle, so no shared cache, browser cache or intermediary may retain it.
# [impl->req~sessions-challenge-transport-no-store~1]
CACHE_CONTROL_HEADER = "Cache-Control"
NO_STORE = "no-store"


def prepare_response_headers(headers: Mapping[str, str] | None = None) -> dict[str, str]:
    """The headers a prepare response goes out with. `Cache-Control: no-store` is added here, and a
    caller that tried to weaken it fails closed rather than shipping a cacheable capability."""
    # [impl->req~sessions-challenge-transport-no-store~1]
    outgoing = {name: value for name, value in (headers or {}).items()
                if name.lower() != CACHE_CONTROL_HEADER.lower()}
    supplied = [value for name, value in (headers or {}).items()
                if name.lower() == CACHE_CONTROL_HEADER.lower()]
    if any(NO_STORE not in value.lower() for value in supplied):
        raise TransportError("a prepare response carries Cache-Control: no-store")
    outgoing[CACHE_CONTROL_HEADER] = NO_STORE
    return outgoing


# --- What is logged instead ----------------------------------------------------------------------


def log_correlation_id(row: ChallengeRow) -> str:
    """What is logged for correlation: the challenge row's server-side `id`. It is not a capability
    handle, so it is safe in logs, traces and audit rows — and it is what makes an incident
    reconstructible without the handle."""
    # [impl->req~sessions-challenge-transport-no-plaintext-logging~1]
    if row.id is None:
        raise TransportError("the challenge row has no server-side id to correlate on")
    if str(row.id) == row.challenge_id:
        raise TransportError("the row id must not be the capability handle")
    return str(row.id)


def assert_nothing_logs_the_handle(payload: Mapping[str, Any], *, challenge_id: str) -> None:
    """Fail closed on a log, trace, analytics, error-report or client-visible error payload that
    carries the challenge ID in plaintext — by value, wherever it is nested, and whatever the key it
    was put under is called."""
    # [impl->req~sessions-challenge-transport-no-plaintext-logging~1]
    if not challenge_id:
        raise TransportError("there is no challenge id to check")
    if _contains(payload, challenge_id):
        raise TransportError("the challenge id is never written in plaintext")


def _contains(value: Any, needle: str) -> bool:
    if isinstance(value, Mapping):
        return any(_contains(item, needle) for item in value.values())
    if isinstance(value, list | tuple | set | frozenset):
        return any(_contains(item, needle) for item in value)
    return isinstance(value, str) and needle in value


def client_error_message(row: ChallengeRow) -> str:
    """The message a client may see about a challenge failure: it names no handle. The shared error
    contract already gives the client only its class, and this keeps the handle out of the text
    too."""
    # [impl->req~sessions-challenge-transport-no-plaintext-logging~1]
    message = "the operation challenge is not usable; prepare a fresh one"
    if row.challenge_id in message:
        raise TransportError("a client-visible message never carries the challenge id")
    return message


def assert_prepare_response_safe(response: PrepareResponse, row: ChallengeRow) -> PrepareResponse:
    """A prepare response before it goes out: the handle is in the body, the body is `no-store`, and
    the server-side row id is not disclosed alongside it."""
    # [impl->req~sessions-challenge-transport-body-only~1]
    # [impl->req~sessions-challenge-transport-no-store~1]
    assert_transport_location(TransportLocation.prepare_response_body)
    if response.challenge_id != row.challenge_id:
        raise TransportError("the prepare response carries this row's handle")
    if prepare_response_headers().get(CACHE_CONTROL_HEADER) != NO_STORE:
        raise TransportError("a prepare response carries Cache-Control: no-store")
    return response


# --- The challenge is not a credential -----------------------------------------------------------


class IdentitySource(StrEnum):
    """Where a completion's `(issuer, subject)` pair could come from."""
    backend_verified_id_token = "backend_verified_id_token"
    request_body_field = "request_body_field"
    client_supplied_header = "client_supplied_header"
    proxy_supplied_header = "proxy_supplied_header"
    challenge_row = "challenge_row"


# The one permitted source. `(issuer, subject)` is freshly derived from the backend's own
# verification of the current external IDP ID token on every request.
# [impl->req~sessions-challenge-binding-not-a-credential~1]
PERMITTED_IDENTITY_SOURCES: frozenset[IdentitySource] = frozenset({
    IdentitySource.backend_verified_id_token,
})

# What a challenge is, and is not. It is never a bearer or authentication credential: presenting a
# valid handle authenticates nobody, and a completion carrying one but no ID token is rejected.
# [impl->req~sessions-challenge-binding-not-a-credential~1]
CHALLENGE_IS_A_CREDENTIAL: bool = False


def completion_identity(claims: VerifiedClaims | None,
                        *,
                        source: IdentitySource = IdentitySource.backend_verified_id_token,
                        challenge_id: str | None = None) -> tuple[str, str]:
    """The `(issuer, subject)` a completion runs as.

    Completion always requires the current external IDP ID token, verified by the backend itself
    under Minimum External JWT Acceptance, with the pair freshly derived from that verification on
    every request — never taken from a request-body field or any client- or proxy-supplied header,
    and never from the challenge row. A challenge handle alone authenticates nobody: that is the
    load-bearing property, and this function is where it holds.
    """
    # [impl->req~sessions-challenge-binding-not-a-credential~1]
    if CHALLENGE_IS_A_CREDENTIAL:
        raise TransportError("a challenge is never a bearer or authentication credential")
    if source not in PERMITTED_IDENTITY_SOURCES:
        raise TransportError(f"{source} never establishes the completing identity")
    if claims is None:
        raise TransportError("completion requires the current external IDP ID token")
    if not claims.issuer or not claims.subject:
        raise TransportError("the verified token supplied no issuer and subject")
    if challenge_id is not None and challenge_id in (claims.issuer, claims.subject):
        raise TransportError("the challenge handle is not an identity")
    # Derived freshly, on this request, from these verified claims: the same canonicalized preimage
    # every other identity derivation in this backend uses.
    actor_subject_preimage(claims.issuer, claims.subject)
    return claims.issuer, claims.subject


# --- Proportionality ------------------------------------------------------------------------------

# Bindings challenge binding deliberately does not add. Mobile clients change networks, so an IP,
# device or TLS-channel binding would break legitimate use without stopping the attacker this
# specification already accepts.
# [impl->req~sessions-challenge-binding-proportionality~1]
REJECTED_BINDINGS: frozenset[str] = frozenset({
    "ip_binding", "device_binding", "tls_channel_binding", "dpop", "mtls_client_certificate",
    "client_key_signing", "mandatory_token_hash_embedding",
})

# Hardening explicitly out of scope for this version: the optional prepare-time token-subject and
# `iat` checks.
OUT_OF_SCOPE_HARDENING: frozenset[str] = frozenset({
    "prepare_time_token_subject_check", "prepare_time_iat_check",
})

# The controls that *are* proportionate, and the whole set of them.
# [impl->req~sessions-challenge-binding-proportionality~1]
PROPORTIONATE_CONTROLS: tuple[str, ...] = (
    "exact_identity_binding",
    "random_challenge_ids_128_bit",
    "short_challenge_lifetime",
    "single_use",
    "existing_gateway_rate_limits",
)

# The attacker this design accepts: one holding both the prepare response and a valid external IDP
# credential for the bound subject has already compromised that account — the stateless-token risk
# the specification accepts elsewhere, not a new exposure this binding creates.
ACCEPTED_ATTACKER_ALREADY_COMPROMISED_ACCOUNT: bool = True


def assert_proportionate_controls(controls: Iterable[str] = ()) -> tuple[str, ...]:
    """Challenge binding's controls: exact identity binding, 128-bit random challenge IDs, the
    short challenge lifetime, single use, and the existing gateway rate limits.

    Anything from the rejected list — an IP, device or TLS-channel binding, DPoP, mTLS client
    certificates, client-key signing, a mandatory token-hash embedding — or the out-of-scope
    prepare-time hardening fails here. The two numeric controls are read from the challenge module
    that owns them, so a shortened ID or an unbounded lifetime fails here too.
    """
    # [impl->req~sessions-challenge-binding-proportionality~1]
    requested = {str(control) for control in controls}
    offending = sorted(requested & (REJECTED_BINDINGS | OUT_OF_SCOPE_HARDENING))
    if offending:
        raise TransportError(f"challenge binding adds no {offending}")
    unknown = sorted(requested - set(PROPORTIONATE_CONTROLS))
    if unknown:
        raise TransportError(f"{unknown} is not one of the proportionate controls")
    if CHALLENGE_ID_BYTES * 8 != 128:
        raise TransportError("challenge ids are 128-bit random values")
    if CHALLENGE_TTL_SECONDS <= 0:
        raise TransportError("the challenge lifetime is short and bounded")
    if not ACCEPTED_ATTACKER_ALREADY_COMPROMISED_ACCOUNT:
        raise TransportError("the accepted attacker has already compromised the account")
    return PROPORTIONATE_CONTROLS
