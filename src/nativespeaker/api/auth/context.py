"""The §1.4 typed identity context -- the one object the barrier attaches on admission.

Handlers consume this and nothing else. A handler must not perform or re-implement JWT acceptance
or identity resolution, and must not reconstruct identity context from claims. Phases 36-46 import
these five symbols by name; the field sets below are the seam, not an implementation detail.

Two rules this module encodes structurally rather than by convention:

- **The stored `ExternalIdentity.provider` column is the sole per-request classifier** for every
  identity, authorization, entitlement, grant-class, and audit decision. `LinkedIdentity` carries
  the resolved row, so reading the classifier means reading the column the database stores. No
  claim-derived provider field exists on this context for a caller to reach for instead, and
  `User.registered_at` is **reporting-only** -- never a competing classifier.
- **`PreAuthIdentity` carries the verified `(issuer, subject)` and nothing else.** No user row, no
  identity row, no provider. A handler holding one cannot read an unlinked subject as if it were
  linked, because there is nothing there to read.

**No client address is carried.** `ClientIpBucketKind` records the bucket kind only. §9 (the Envoy
gateway contract) is deferred to the next milestone, so `xff_num_trusted_hops` is unpinned and any
address stored here would be trusted rather than proven (A3). §4.4 needs the kind, not the address.
The kind is derived once, from the gateway-resolved `scope["client"]`, and is **never** recomputed
from raw forwarded headers -- by this module or any later one.
"""
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from nativespeaker.api.auth.registry import RouteMetadata
from nativespeaker.api.models.identities import ExternalIdentity
from nativespeaker.api.models.users import User

# The key the barrier stashes the context under, on `scope["state"]` / `request.state`. Pinned as a
# module constant so the writer (the barrier) and the readers (the `Depends()` accessors) cannot
# drift to two different strings, which would fail open as a missing context rather than loudly.
REQUEST_CONTEXT_SCOPE_KEY = "ns_request_context"


class IdentityKind(StrEnum):
    """The discriminator tag on the two §1.4 variants."""
    linked = "linked"
    preauth = "preauth"


class ClientIpBucketKind(StrEnum):
    """The client-address bucket kind (§4.4). The address itself is deliberately not carried."""
    ipv4 = "ipv4"
    ipv6 = "ipv6"
    unresolved = "unresolved"


@dataclass(frozen=True, slots=True)
class LinkedIdentity:
    """A verified `(issuer, subject)` resolved through an active identity row to an active user.

    `kind` sits last and defaults, so the tag cannot be omitted or mis-set at a construction site:
    a dataclass cannot carry a defaulted field ahead of undefaulted ones, and the `Literal`
    annotation makes the wrong member a type error rather than a runtime discriminator bug.
    """
    user: User
    identity: ExternalIdentity
    issuer: str
    subject: str
    kind: Literal[IdentityKind.linked] = IdentityKind.linked


@dataclass(frozen=True, slots=True)
class PreAuthIdentity:
    """A verified `(issuer, subject)` that resolved to no identity row -- and nothing else.

    No user, no identity row, no provider, and no `user`-keyed limiter is available for such a
    request. Adding a field here would hand a handler exactly the unlinked-read-as-linked path
    §1.4 exists to make unrepresentable.
    """
    issuer: str
    subject: str
    kind: Literal[IdentityKind.preauth] = IdentityKind.preauth


@dataclass(frozen=True, slots=True)
class RequestContext:
    """The request-scoped values later phases read and must never recompute (§1.4).

    `evaluated_at` is the single captured evaluation time for the whole request -- every
    time-dependent value derives from it, so two reads within one request can never straddle a
    period boundary. `attempt_id` is server-generated and never taken from client input.
    """
    identity: LinkedIdentity | PreAuthIdentity
    route_metadata: RouteMetadata
    client_ip_bucket_kind: ClientIpBucketKind
    evaluated_at: datetime
    attempt_id: UUID
