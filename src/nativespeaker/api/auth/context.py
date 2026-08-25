"""The typed identity context: the one object admission produces and handlers consume."""
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from nativespeaker.api.models.identities import ExternalIdentity
from nativespeaker.api.models.users import User


class IdentityKind(StrEnum):
    """The discriminator tag on the two identity variants."""
    linked = "linked"
    preauth = "preauth"


@dataclass(frozen=True, slots=True)
class LinkedIdentity:
    """A verified `(issuer, subject)` resolved through an active identity row to an active user."""
    user: User
    identity: ExternalIdentity  # the stored provider column is the only per-request classifier
    issuer: str
    subject: str
    kind: Literal[IdentityKind.linked] = IdentityKind.linked


@dataclass(frozen=True, slots=True)
class PreAuthIdentity:
    """A verified `(issuer, subject)` that matched no identity row, and deliberately nothing else."""
    # Adding a user, identity or provider field here would let a handler read unlinked as linked.
    issuer: str
    subject: str
    kind: Literal[IdentityKind.preauth] = IdentityKind.preauth


@dataclass(frozen=True, slots=True)
class RequestContext:
    """The request-scoped values later phases read and never recompute."""
    identity: LinkedIdentity | PreAuthIdentity
    route: str  # matched path template like /chats/{chat_id}; a concrete path unbounds log and quota keys
    evaluated_at: datetime  # the single evaluation time for the whole request; nothing recomputes it
    attempt_id: UUID  # server-generated, never taken from client input
