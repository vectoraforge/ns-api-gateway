"""The §1.4 typed identity context -- the one object admission produces.

Handlers consume this and nothing else. A handler must not perform or re-implement JWT acceptance
or identity resolution, and must not reconstruct identity context from claims. Phases 36-46 import
these four symbols by name; the field sets below are the seam, not an implementation detail.

Two rules this module encodes structurally rather than by convention:

- **The stored `ExternalIdentity.provider` column is the sole per-request classifier** for every
  identity, authorization, entitlement, grant-class, and audit decision. `LinkedIdentity` carries
  the resolved row, so reading the classifier means reading the column the database stores. No
  claim-derived provider field exists on this context for a caller to reach for instead, and
  `User.registered_at` is **reporting-only** -- never a competing classifier.
- **`PreAuthIdentity` carries the verified `(issuer, subject)` and nothing else.** No user row, no
  identity row, no provider. A handler holding one cannot read an unlinked subject as if it were
  linked, because there is nothing there to read.

**No client address is carried, in any form.** §9 (the Envoy gateway contract) is deferred to the
next milestone, so `xff_num_trusted_hops` is unpinned and any address stored here would be trusted
rather than proven (A3). Nothing on this context is derived from the client address, and no later
module may recompute one from `X-Forwarded-For`, `Forwarded`, or any other client-supplied header.
"""
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from nativespeaker.api.models.identities import ExternalIdentity
from nativespeaker.api.models.users import User


class IdentityKind(StrEnum):
    """The discriminator tag on the two §1.4 variants."""
    linked = "linked"
    preauth = "preauth"


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

    `route` is the matched route's **path template** -- `/chats/{chat_id}`, never the concrete
    `/chats/9f2.../`. It is the route identity the rejection log and the quota charge are keyed on,
    and a template keeps both bounded: a concrete path would put an unbounded set of client-chosen
    values into a log field and a quota key.
    """
    identity: LinkedIdentity | PreAuthIdentity
    route: str
    evaluated_at: datetime
    attempt_id: UUID
