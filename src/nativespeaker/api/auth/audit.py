"""§4 audit writer -- two write modes, one row builder, one `details` shape, redaction before write.

`§4.1` makes auditing an obligation of the audited attempt path: exactly one row per on-path
attempt, for its terminal outcome, written before the response returns. A request is on the path if
and only if the matched route+method carries an `operation` in its metadata -- never because of how
far the handler ran or which phase rejected.

**No production request in Phase 35 is on that path.** All eight routes foundation registers
declare `operation = None`, and `§8.2` puts them off the path permanently. The writer is built and
proven here; phases 37-45 supply the real call sites.

Three rules this module encodes structurally rather than by convention:

- **The derivation is not reimplemented here.** `actor_subject_hash` comes from
  `HmacKeyring.actor_subject_hash`, the same method the challenge store calls for
  `preauth_subject_hash` (D-21). This module imports no `hmac`, no `hashlib`, no `base64` -- a
  second derivation would drift silently, because both forms produce a plausible 32-byte digest and
  only one matches the rows already written.
- **The writer refuses to build a row the table would reject.** `audit.auth_events` admits
  all-NULL actor fields for `invalid_external_jwt` alone; every other result requires issuer,
  subject hash, and key version. Raising here with a message naming the problem beats a constraint
  violation at insert time. RESEARCH Pitfall 10 is the case that makes this matter: an
  `internal_error` row for an unresolvable user *cannot* carry NULL actors, and at that point the
  token has been verified, so issuer and subject are known and must be populated.
- **`audit.auth_events` is not a proof archive.** Redaction runs before every write and drops the
  full `§4.4` list at any nesting depth. Not the raw client address either, nor a device or install
  identifier, nor any other stable per-client identifier -- only the client-IP *bucket kind*, so
  the audit log cannot become a behavioural-tracking archive.

What each row must still suffice to reconstruct: the verified actor when one exists (or that none
was available), which non-secret challenge row was involved, which operation was attempted, which
non-secret verification and identity metadata were available, what state changed including partial
state, and why the request was rejected.
"""
from collections.abc import Mapping
from datetime import date, datetime
from enum import Enum
from typing import Any
from uuid import UUID

import structlog
from sqlmodel.ext.asyncio.session import AsyncSession

from nativespeaker.api.auth.keys import HmacKeyring
from nativespeaker.api.models.auth import AuthEvent, AuthEventResult, AuthOperation
from nativespeaker.api.models.identities import IdentityProvider

logger = structlog.get_logger()

# The `details.schema_version` every row this phase writes carries. Bump it only alongside a
# migration that can read both shapes.
DETAILS_SCHEMA_VERSION = 1

# §4.4's top level, exactly. The table CHECKs each of these six independently, which is why
# building the object in one place is what stops a caller shipping five keys.
DETAILS_SUBOBJECTS = ("context", "verification", "resolved", "mutation", "failure")
DETAILS_KEYS = ("schema_version", *DETAILS_SUBOBJECTS)

# The one result the all-or-nothing actor CHECK admits with no actor at all.
_NO_ACTOR_RESULT = AuthEventResult.invalid_external_jwt

# §4.4's redaction list as exact key names: a key equal to one of these is dropped wherever it
# appears. Names too short or too generic to match as a fragment live here rather than below.
FORBIDDEN_KEY_NAMES = frozenset({
    # raw JWTs and every other bearer credential
    "authorization", "bearer", "credential", "credentials", "jwt",
    # the raw verified subject -- only the keyed hash is ever durable, and it lives in a column
    "sub", "subject", "actor_subject",
    # the public challenge capability handle under a short name
    "challenge",
    # stable per-client identifiers: device, install, and vendor handles
    "device", "idfa", "idfv", "install_id", "installation_id", "vendor_id",
    # raw provider account identifiers
    "provider_account", "provider_account_id", "provider_uid",
    # raw client addresses
    "client_ip", "ip", "peer_ip", "remote_ip",
})

# Case-insensitive fragments: a key *containing* one of these is dropped wherever it appears.
# Substring matching is what makes the redactor total over field names later phases have not
# invented yet, which an exact list can never be. Over-redaction is the safe direction here.
FORBIDDEN_KEY_FRAGMENTS = (
    "addr",                 # client_address, remote_addr, peer_address -- the bucket kind survives
    "attestation",          # attestation blobs and attestation private keys
    "challenge_id",         # the public handle; `challenge_row_id` does not contain this fragment
    "device_fingerprint",
    "device_id",
    "email",                # email addresses
    "password",
    "payload",              # signed transaction payloads
    "private_key",
    "proof",                # raw restore_proof
    "provider_response",    # raw provider responses
    "raw_",                 # raw anything: raw_token, raw_response, raw_subject, raw_device_id
    "secret",
    "signature",
    "signed_",              # signed transaction payloads
    "token",                # raw JWTs, purchase tokens, refresh tokens, id tokens
)


def _is_forbidden(key: str) -> bool:
    name = key.strip().lower()
    return name in FORBIDDEN_KEY_NAMES or any(f in name for f in FORBIDDEN_KEY_FRAGMENTS)


def _jsonable(value: Any) -> Any:
    """Coerce a leaf to something `JSONB` can hold.

    The alternative is an unserializable `UUID` or `datetime` reaching the driver and failing the
    insert -- which the write wrapper would swallow, making a lost audit row the *quiet* outcome.
    Coercing is cheap insurance against exactly that.
    """
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, Enum):  # StrEnum included -- store the value, never the member repr
        return value.value
    if isinstance(value, str):
        return value
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    return str(value)


def _copy_mapping(payload: Mapping[str, Any], *, drop_forbidden: bool) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in payload.items():
        name = str(key)
        if drop_forbidden and _is_forbidden(name):
            continue
        out[name] = _copy_value(value, drop_forbidden=drop_forbidden)
    return out


def _copy_value(value: Any, *, drop_forbidden: bool) -> Any:
    if isinstance(value, Mapping):
        return _copy_mapping(value, drop_forbidden=drop_forbidden)
    # `str` and `bytes` are iterable but are leaves; only real containers are walked, and a
    # forbidden key nested inside one still gets dropped.
    if isinstance(value, list | tuple | set | frozenset):
        return [_copy_value(item, drop_forbidden=drop_forbidden) for item in value]
    return _jsonable(value)


def build_details(*,
                  context: Mapping[str, Any] | None = None,
                  verification: Mapping[str, Any] | None = None,
                  resolved: Mapping[str, Any] | None = None,
                  mutation: Mapping[str, Any] | None = None,
                  failure: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Build the §4.4 object: exactly six top-level keys, every subobject present.

    - `context` -- non-secret request and routing context: route, method, operation, attempt id,
      mode signals as booleans, and the client-IP **bucket kind** (never the address).
    - `verification` -- which proof families were checked, verifier error codes, adapter attempt
      counts, budget names consulted.
    - `resolved` -- resolved internal ids and redacted server-derived identifiers.
    - `mutation` -- the actual committed state change, **including partial state on fail-closed
      paths**; `{}` where nothing changed.
    - `failure` -- rejection stage, machine-readable reason context including the bounded
      `invalid_external_jwt` reason, and retryability metadata; `{}` on a successful event.

    The parameters are keyword-only and named, so a seventh top-level key is a `TypeError` at the
    call site rather than a row the table's CHECK rejects at insert time. Redaction is *not*
    applied here -- `AuditWriter` applies it to whatever it is handed, so a caller that skips this
    builder still cannot write a secret.
    """
    return {
        "schema_version": DETAILS_SCHEMA_VERSION,
        "context": _subobject(context),
        "verification": _subobject(verification),
        "resolved": _subobject(resolved),
        "mutation": _subobject(mutation),
        "failure": _subobject(failure),
    }


def _subobject(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    return {} if payload is None else _copy_mapping(payload, drop_forbidden=False)


def redact(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Drop every forbidden key at any nesting depth, returning a new object.

    The argument is never mutated: a caller that logs or asserts against the object it built still
    sees what it built. Keys are *dropped*, not masked -- a `"raw_token": "[REDACTED]"` entry still
    tells a reader which field was present, and the name itself is sometimes the disclosure.

    A top-level-only redactor is the failure mode that looks correct in review, so the walk
    recurses through mappings *and* through lists, tuples, and sets.
    """
    return _copy_mapping(payload, drop_forbidden=True)


class AuditWriter:
    """§4.1's two modes over one row builder (D-19).

    Both modes build the row identically; they differ only in the session they use and whether they
    commit. One instance lives on `app.state.audit_writer` -- read it per request, never cache it.
    """

    def __init__(self, keyring: HmacKeyring) -> None:
        self._keyring = keyring

    def __repr__(self) -> str:
        return f"AuditWriter(key_version={self._keyring.active_version})"

    def build_row(self, *,
                  operation: AuthOperation | None,
                  result: AuthEventResult,
                  actor_issuer: str | None,
                  actor_subject: str | None,
                  actor_provider: IdentityProvider | None,
                  challenge_row_id: UUID | None,
                  details: Mapping[str, Any],
                  created_at: datetime) -> AuthEvent:
        """Build the row both modes write, raising before any database work if it cannot be legal.

        `actor_subject` arrives raw and leaves hashed: the raw subject is never stored, logged, or
        returned. `actor_provider` is the caller's business -- it may come only from the stored
        `core.external_identities.provider` column of a resolved linked identity, and is NULL for
        pre-auth and unresolved events.
        """
        _assert_actor_consistency(result, actor_issuer, actor_subject, actor_provider)
        _assert_details_shape(details)

        subject_hash = None
        key_version = None
        if actor_issuer is not None and actor_subject is not None:
            subject_hash = self._keyring.actor_subject_hash(actor_issuer, actor_subject)
            key_version = self._keyring.active_version

        return AuthEvent(operation=operation,
                         result=result,
                         actor_issuer=actor_issuer,
                         actor_subject_hash=subject_hash,
                         actor_subject_hash_key_version=key_version,
                         actor_provider=actor_provider,
                         challenge_row_id=challenge_row_id,
                         details=redact(details),
                         created_at=created_at)

    async def write_standalone(self, session_factory, *,
                               operation: AuthOperation | None,
                               result: AuthEventResult,
                               actor_issuer: str | None,
                               actor_subject: str | None,
                               actor_provider: IdentityProvider | None,
                               challenge_row_id: UUID | None,
                               details: Mapping[str, Any],
                               created_at: datetime) -> None:
        """Standalone-durable mode: the attempt was rejected before any consuming transaction.

        The factory is a parameter rather than app state read here, so the writer never caches
        `app.state.session_factory` and the e2e rollback fixture's per-test swap still governs
        (Pitfall 5). The `commit()` is what `§4.1` means by "before the response returns"; under
        the harness's `join_transaction_mode="create_savepoint"` it releases a savepoint rather
        than the outer transaction, so the row is visible to a session on the same connection and
        still rolls back at the end of the test.
        """
        event = self.build_row(operation=operation, result=result, actor_issuer=actor_issuer,
                               actor_subject=actor_subject, actor_provider=actor_provider,
                               challenge_row_id=challenge_row_id, details=details,
                               created_at=created_at)
        try:
            async with session_factory() as session:
                session.add(event)
                await session.commit()
        except Exception:
            _log_failure(event)

    async def write_in_transaction(self, session: AsyncSession, *,
                                   operation: AuthOperation | None,
                                   result: AuthEventResult,
                                   actor_issuer: str | None,
                                   actor_subject: str | None,
                                   actor_provider: IdentityProvider | None,
                                   challenge_row_id: UUID | None,
                                   details: Mapping[str, Any],
                                   created_at: datetime) -> None:
        """In-consuming-transaction mode: written inside the caller's session, atomically with
        challenge consumption and any state change, and **not** committed.

        The flush is what makes the row visible to that session before its commit. If it fails the
        caller's transaction is poisoned and their own commit will say so -- which is the right
        place for it to surface, because that transaction owns the state change this row describes.
        """
        event = self.build_row(operation=operation, result=result, actor_issuer=actor_issuer,
                               actor_subject=actor_subject, actor_provider=actor_provider,
                               challenge_row_id=challenge_row_id, details=details,
                               created_at=created_at)
        try:
            session.add(event)
            await session.flush()
        except Exception:
            _log_failure(event)


def _assert_actor_consistency(result: AuthEventResult,
                              actor_issuer: str | None,
                              actor_subject: str | None,
                              actor_provider: IdentityProvider | None) -> None:
    """The all-or-nothing actor CHECK, enforced early enough to be diagnosable (T-35-09-08).

    `invalid_external_jwt` means verification supplied no permitted actor, so a value in any actor
    column means the caller invented one -- checked in both directions, because the CHECK is.
    """
    if result is _NO_ACTOR_RESULT:
        present = [name for name, value in (("actor_issuer", actor_issuer),
                                            ("actor_subject", actor_subject),
                                            ("actor_provider", actor_provider)) if value is not None]
        if present:
            raise ValueError(f"result {result} admits no actor at all, but "
                             f"{', '.join(present)} was supplied: verification produced no "
                             f"permitted actor, so no actor column may be filled")
        return

    missing = [name for name, value in (("actor_issuer", actor_issuer),
                                        ("actor_subject", actor_subject)) if value is None]
    if missing:
        raise ValueError(f"result {result} requires every actor field, but {', '.join(missing)} "
                         f"is None: at this point the token has been verified, so the issuer and "
                         f"subject are known and must be populated "
                         f"(actor_provider stays None when no identity row resolved)")


def _assert_details_shape(details: Mapping[str, Any]) -> None:
    """§4.4's six keys, enforced early for the same reason the actor guard is."""
    if set(details) != set(DETAILS_KEYS):
        raise ValueError(f"details must carry exactly {sorted(DETAILS_KEYS)}, got "
                         f"{sorted(details)}: build it with build_details()")
    empty = [key for key in DETAILS_SUBOBJECTS if not isinstance(details[key], Mapping)]
    if empty:
        raise ValueError(f"details subobjects must be objects, but {', '.join(empty)} is not")


def _log_failure(event: AuthEvent) -> None:
    """Auditing is never best-effort, but it never changes the client's outcome either (§4.1).

    The caller still returns exactly what the attempt earned -- never a different outcome, never a
    500 substituted for a business rejection. The line carries enough to find the lost row and
    nothing more: no raw subject, no `details`, no bounded reason.
    """
    logger.exception("audit_write_failed",
                     event_id=str(event.id),
                     result=str(event.result),
                     operation=None if event.operation is None else str(event.operation),
                     has_actor=event.actor_issuer is not None,
                     challenge_row_id=None if event.challenge_row_id is None
                     else str(event.challenge_row_id))
