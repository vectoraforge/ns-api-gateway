"""The §7 adapter seams: interfaces, result types, and nothing else.

Foundation defines the seams, the request/response types, and the error taxonomy. It implements
**no** provider call -- not one `firebase_admin` import, not one network client, not one line of
I/O at import time. `get_user_provider_data` is called exactly zero times here; §7.1 pins exactly
five providerData read points in the whole system and every one of them is in a later phase. Every
concrete adapter belongs to the phase named beside it below, and
`tests/unit/test_adapter_interfaces.py` fails the moment one appears in this module.

**The shared rules every concrete adapter must satisfy** (§7's preamble). They are recorded here,
at the seam, rather than in each implementing phase, because a rule restated four times is a rule
that drifts three ways:

- **no provider call while a database lock is held** or a transaction is open. Provider latency
  under a row lock converts a slow vendor into a database-wide stall;
- every outbound call carries a **fixed configured per-attempt timeout** on the order of
  **5-10 seconds**. Fixed and configured, never unbounded and never per-call ad hoc;
- adapter failures map into the shared error taxonomy (`nativespeaker.api.errors`) and
  **never leak provider text to clients**. A provider's message is diagnostic material for the
  audit row and the log, never for the response body.

**Retry wiring.** §7.1's 3-attempt budget on the providerData read is expressed with `tenacity`
in `auth/retry.py` (`FIREBASE_LOOKUP_ATTEMPTS`, `lookup_with_retry`), and only
`ProviderDataOutcome.retryable_failure` is retried. `user_not_found` and `selection_failure` are
definitive: they resolve on the first attempt and spend no further one. Exhausting the three
attempts is not a rate-limit rejection -- it maps to internal `firebase_lookup_unavailable` ->
client `verification_temporarily_unavailable`, and `auth/retry.py` carries that pair as named
constants rather than as a literal repeated at each call site.

**Why these are `Protocol`s and not ABCs.** Nothing here is inherited from. A concrete adapter in
phase 08 satisfies `StoreAdapter` structurally, which keeps the dependency arrow pointing at
foundation without foundation owning a base class that later phases must import and instantiate.
None is `@runtime_checkable`: an `isinstance` pass over method *names* would assert nothing about
the contracts below, and having it available invites exactly that false comfort.
"""
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from nativespeaker.api.auth.verification import VerifiedClaims

# ---------------------------------------------------------------------------
# §7.1 Issuer-selected Firebase Admin integration
# ---------------------------------------------------------------------------


class ProviderDataOutcome(StrEnum):
    """The closed §7.1 outcome set for a `getUser` providerData read. Exactly four, no more."""

    ok = "ok"
    # Definitive and **non-retryable**: it spends no retry budget and rejects immediately. Maps to
    # internal `firebase_user_unresolved` -> client `auth_required`. Metering it as a retryable
    # failure would burn two further attempts proving a fact Firebase already stated.
    user_not_found = "user_not_found"
    # Outage, malformed or indeterminate response, integration-auth failure. The only outcome the
    # 3-attempt budget is for.
    retryable_failure = "retryable_failure"
    # Issuer mismatch. Fails closed and **never falls back to another project** -- there is one
    # configured integration and one client selected by issuer match, and no ambient, default,
    # global, or fallback client is expressible through this seam.
    selection_failure = "selection_failure"


class RevocationOutcome(StrEnum):
    """Two-valued on purpose (§7.1).

    `confirmed` only when Firebase confirmed revocation for the subject. Every other outcome --
    definitive Firebase error, permission/configuration or quota failure, timeout, lost response,
    or an exhausted retry budget -- is `unconfirmed`, and maps to internal `revocation_unconfirmed`.
    A third member would let a caller treat "probably worked" as success, which is the one reading
    a sign-out-everywhere contract cannot afford.
    """

    confirmed = "confirmed"
    unconfirmed = "unconfirmed"


@dataclass(frozen=True, slots=True)
class ProviderDataEntry:
    """One entry of a `getUser` providerData response.

    The two fields the classifier is pinned to: the provider id (`google.com`, `apple.com`) and the
    account's uid at that provider. The **classification rule itself is phase 02's**, not
    foundation's -- empty means anonymous, exactly one recognized entry means that provider, and
    every other shape rejects. Foundation reads zero entries, so it declares the shape and stops
    there; the "never take the first recognized entry" rule lives with the code that classifies.
    """

    provider_id: str
    uid: str


@dataclass(frozen=True, slots=True)
class ProviderDataResult:
    """§7.1 `ok(provider_data_entries)` and the three failure outcomes, as one closed result.

    `entries` is populated only for `ok` and is empty otherwise, which is also the honest reading
    of an `ok` for an account with no linked provider -- an empty providerData is a fact, not a
    failure.
    """

    outcome: ProviderDataOutcome
    entries: tuple[ProviderDataEntry, ...] = ()


class FirebaseAdminAdapter(Protocol):
    """§7.1. One configured integration; one Admin client selected by issuer match.

    The adapter never falls back to a client declaration, token claim, header, email, display name,
    or cached value. `issuer` is a parameter of both lookup methods so selection happens per call
    and no ambient client is reachable.
    """

    def verify_id_token(self, raw_token: str) -> VerifiedClaims:
        """Verify an external ID token against the selected integration (§1.2's rules).

        Note the barrier does **not** call this: it holds a `TokenVerifier` (auth/verification.py),
        whose `verify` returns `(claims, reason)` rather than raising, because the barrier is
        installed with `add_middleware` and sits outside Starlette's `ExceptionMiddleware` (D-01).
        This is §7.1's declaration of the same capability behind the issuer-selected Admin client,
        for the later phases that call it from inside a handler, where raising is the idiom.
        """
        ...

    def get_user_provider_data(self, issuer: str, subject: str) -> ProviderDataResult:
        """The `getUser` providerData read. Retry-gated; never called on an ordinary request path.

        There are exactly five enumerated read points in the whole system (phases 02, 05, 06, 07).
        Foundation calls this zero times, and no ordinary request path may call it at all.
        """
        ...

    def revoke_refresh_tokens(self, issuer: str, subject: str) -> RevocationOutcome:
        """The refresh-token revocation seam phase 11 (`sign-out-all`) calls.

        Same issuer-selected client rule: an issuer mismatch fails closed before any Admin call.
        Foundation declares the signature and the two-valued result only -- phase 11 owns the call
        site, its own attempt count, and any in-flight coalescing, and expresses the retry with the
        `auth/retry.py` tenacity idiom rather than a second hand-rolled loop.
        """
        ...


# ---------------------------------------------------------------------------
# §7.2 Store-verification adapter
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class VerifiedNotification:
    """A provider callback whose credential the named verifier proved (§7.2).

    Two fields, because two are what the seam itself needs: which named verifier proved it, and
    the provider's own stable notification identity -- the idempotency key phases 08/09 insert on.
    The rest of the payload is provider-shaped and §7.2 pins no further field, so foundation
    declares none rather than guessing at Apple's and Google's envelopes on their behalf.
    """

    provider: str
    route_verifier_id: str
    notification_id: str


@dataclass(frozen=True, slots=True)
class VerifiedTransaction:
    """A verified client-presented store artifact, resolved (§7.2).

    Carries the resolved `(provider, external_id)`, the transaction's stable identity (Apple
    `originalTransactionId`; the Play purchase token plus its linked purchase), any carried
    purchase UUID, and the store-checked app/product/environment context that the verification
    itself checked -- not values the client asserted.
    """

    provider: str
    external_id: str
    transaction_identity: str
    purchase_uuid: UUID | None
    app_id: str
    product_id: str
    environment: str


@dataclass(frozen=True, slots=True)
class StoreState:
    """One live store-state observation for a `(provider, external_id)` (§7.2).

    `observed_at` is the server-issued verification timestamp: it is what the freshness bound is
    measured against, and what the audit row records. It is never taken from the provider payload.
    """

    provider: str
    external_id: str
    entitled: bool
    observed_at: datetime


class StoreAdapter(Protocol):
    """§7.2. Verifying and reading store state, implemented by phases 08, 09, and 10.

    **Rejection distinguishes nothing.** All three methods return `None` for every negative
    outcome, so malformed material and unverifiable material are one indistinguishable answer to
    the client. A richer rejection type here would be an oracle by construction.

    **The coalescing seam is a later-phase obligation, recorded and not built.** Concurrent lookups
    for the same server-derived resource key must be serialized or coalesced so concurrent attempts
    do not each spend a provider call; a coalesced follower makes no outbound call and consumes no
    separate budget unit; a coalesced result is reusable only while fresh under the configured
    freshness bound; and what is shared is the raw store-state observation only -- every follower
    independently completes its own authorization, conflict checks, and transactional processing.
    Phase 10 owns it.
    """

    def verify_provider_callback(self, route_verifier_id: str, request: object) -> VerifiedNotification | None:
        """The named-verifier seam the route registry's `named_verifier` field points at (§2.1).

        `route_verifier_id` names the verifier, so a route can never be served by a verifier it did
        not declare, and a missing verifier configuration fails closed at startup rather than at
        the first callback.
        """
        ...

    def verify_store_artifact(self, provider: str, artifact: str) -> VerifiedTransaction | None:
        """Verify a **client-presented** store artifact and resolve it.

        Takes the submitted artifact rather than a resolved pair on purpose: the resolved
        `(provider, external_id)` is an *output* of verification, so a caller cannot assert an
        identity and have the adapter confirm it.
        """
        ...

    def fetch_subscription_state(self, provider: str, external_id: str) -> StoreState | None:
        """Live store-state read, subject to its named provider-call budget and the coalescing seam.

        `None` is `unavailable`, and unavailable always rejects -- there is no "assume entitled"
        reading of a failed live verification.
        """
        ...


# ---------------------------------------------------------------------------
# §7.3 Vendor proof adapter
# ---------------------------------------------------------------------------


class ClaimKind(StrEnum):
    """Which device slot a vendor-proof call addresses (§7.3).

    `anonymous` is iOS DeviceCheck bit0 and the corresponding Android Device Recall state;
    `registered` is bit1. Phase 06 passes `anonymous` only and phase 07 `registered` only.
    """

    anonymous = "anonymous"
    registered = "registered"


class DeviceBitState(StrEnum):
    """§7.3 `bit_state | unavailable`, as one closed three-member set.

    `unavailable` is never read as `unset`: an unreadable bit fails the grant closed rather than
    granting on the assumption that nothing was claimed.
    """

    set = "set"
    unset = "unset"
    unavailable = "unavailable"


class VendorProofAdapter(Protocol):
    """§7.3. Free-grant device-check and bot-check material, implemented by phases 06 and 07.

    **No value from this adapter -- raw, hashed, transaction-scoped, install-scoped, or otherwise
    derived -- may ever become a rate-limit key component or a synthetic device principal.** Not in
    this phase and not in any later one. There is no device-fingerprint key in any form, and no
    stable device principal may be derived to serve as one. All results are pass/fail proof gates
    and nothing else; the moment one is used to *identify* rather than to *gate*, it has become the
    tracking identifier this prohibition exists to prevent.

    The `claim_kind` parameter is what makes the never-touch-the-other-slot invariant structural:
    the **adapter** pins the bit, so phase 06 cannot reach phase 07's slot even by mistake. Each
    call is gated by its own named fail-closed budget, checked immediately before the call it
    budgets, and neither read nor write may be served from a coalesced or cached value.
    """

    def read_device_bit(self, platform: str, claim_kind: ClaimKind, material: str) -> DeviceBitState:
        """Read the slot `claim_kind` selects. Never served from a coalesced or cached value."""
        ...

    def write_device_bit(self, platform: str, claim_kind: ClaimKind, material: str) -> bool:
        """Write the slot `claim_kind` selects. `True` means the vendor confirmed the write.

        The write is **load-bearing and never best-effort**: never deferred, queued, or retried out
        of band, and it must be vendor-confirmed before a grant row is inserted. An unconfirmed
        write is a failed claim, not a claim to reconcile later.
        """
        ...

    def verify_integrity_verdict(self, material: str) -> object | None:
        """Verify an attestation/integrity verdict. `None` is rejected-or-unavailable, undistinguished.

        The verdict's own shape is the implementing phase's (06/07); foundation neither parses nor
        stores it, and no part of it may be retained as an identifier.
        """
        ...

    def verify_bot_check(self, token: str, remote_ip: str | None) -> bool | None:
        """Bot-check verification. `True` ok, `False` rejected, `None` unavailable.

        `remote_ip` is the gateway-resolved address passed through to the vendor and is never
        recomputed from raw forwarded headers, never stored, and never keyed on.
        """
        ...
